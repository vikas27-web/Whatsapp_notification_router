import os
import csv
from datetime import datetime

class DataLoader:
    def __init__(self, dataset_dir):
        self.dataset_dir = dataset_dir
        self.users = {}
        self.groups = {}
        self.group_members = {}  # key: (group_id, user_id)
        self.business_accounts = {}
        self.user_business_history = {}  # key: (user_id, business_id)
        self.message_history = []
        self.message_events = {}  # key: (user_id, message_id)
        self.images = {}  # key: image_id
        self.voice_notes = {}  # key: voice_note_id
        self.daily_notification_summary = {}  # key: user_id -> list of summaries
        
        self.load_all()

    def _read_csv(self, filename):
        path = os.path.join(self.dataset_dir, filename)
        if not os.path.exists(path):
            return []
        with open(path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            return list(reader)

    def load_all(self):
        # 1. Load users
        for row in self._read_csv('users.csv'):
            self.users[row['user_id']] = row
            
        # 2. Load groups
        for row in self._read_csv('groups.csv'):
            self.groups[row['group_id']] = row
            
        # 3. Load group members
        for row in self._read_csv('group_members.csv'):
            self.group_members[(row['group_id'], row['user_id'])] = row
            
        # 4. Load business accounts
        for row in self._read_csv('business_accounts.csv'):
            self.business_accounts[row['business_id']] = row
            
        # 5. Load user business history
        for row in self._read_csv('user_business_history.csv'):
            self.user_business_history[(row['user_id'], row['business_id'])] = row
            
        # 6. Load message history indexed by user_id for high performance
        self.message_history = self._read_csv('message_history.csv')
        self.message_history_by_user = {}
        for row in self.message_history:
            u_id = row['user_id']
            if u_id not in self.message_history_by_user:
                self.message_history_by_user[u_id] = []
            self.message_history_by_user[u_id].append(row)
            
        # 7. Load message events
        for row in self._read_csv('message_events.csv'):
            self.message_events[(row['user_id'], row['message_id'])] = row
            
        # 8. Load images
        for row in self._read_csv('images.csv'):
            self.images[row['image_id']] = row['file_path']
            
        # 9. Load voice notes
        for row in self._read_csv('voice_notes.csv'):
            self.voice_notes[row['voice_note_id']] = row['file_path']
            
        # 10. Load daily notification summary
        for row in self._read_csv('daily_notification_summary.csv'):
            u_id = row['user_id']
            if u_id not in self.daily_notification_summary:
                self.daily_notification_summary[u_id] = []
            self.daily_notification_summary[u_id].append(row)

    def get_user_fatigue(self, user_id):
        summaries = self.daily_notification_summary.get(user_id, [])
        if not summaries:
            return {"avg_dismiss_rate": 0.0, "total_sent_30d": 0}
        
        total_sent = 0
        total_dismissed = 0
        for s in summaries:
            try:
                total_sent += int(s['notifications_sent'])
                total_dismissed += int(s['notifications_dismissed'])
            except ValueError:
                pass
        
        dismiss_rate = total_dismissed / total_sent if total_sent > 0 else 0.0
        return {
            "avg_dismiss_rate": round(dismiss_rate, 3),
            "total_sent_30d": total_sent
        }

    def get_historical_precedents(self, user_id, sender_id=None, group_id=None, business_id=None):
        precedents = []
        user_msgs = self.message_history_by_user.get(user_id, [])
        for msg in user_msgs:
            match = False
            if sender_id and msg['sender_user_id'] == sender_id:
                match = True
            elif group_id and msg['group_id'] == group_id:
                match = True
            elif business_id and msg['business_id'] == business_id:
                match = True
                
            if match:
                event = self.message_events.get((user_id, msg['message_id']), {})
                precedents.append({
                    "message_id": msg['message_id'],
                    "created_at": msg['created_at'],
                    "message_text": msg['message_text'],
                    "media_type": msg['media_type'],
                    "media_id": msg['media_id'],
                    "opened": event.get('message_opened', '0'),
                    "replied": event.get('message_replied', '0'),
                    "dismissed": event.get('notification_dismissed', '0'),
                    "reported": event.get('message_reported', '0'),
                    "muted_after": event.get('muted_after_message', '0')
                })
        # Sort by date descending
        precedents.sort(key=lambda x: x['created_at'], reverse=True)
        return precedents

    def get_message_context(self, message):
        user_id = message['user_id']
        conv_type = message['conversation_type']
        group_id = message['group_id']
        business_id = message['business_id']
        sender_user_id = message['sender_user_id']
        
        context = {
            "message_id": message['message_id'],
            "created_at": message['created_at'],
            "message_text": message['message_text'],
            "media_type": message['media_type'],
            "media_id": message['media_id'],
            "forwarded_count": message['forwarded_count'],
            "conversation_type": conv_type,
            
            # User properties
            "user": self.users.get(user_id, {}),
            "user_fatigue": self.get_user_fatigue(user_id),
        }
        
        # Join group contexts
        if conv_type == 'group' and group_id:
            context["group"] = self.groups.get(group_id, {})
            context["group_membership"] = self.group_members.get((group_id, user_id), {})
            if sender_user_id:
                context["sender_membership"] = self.group_members.get((group_id, sender_user_id), {})
            context["history"] = self.get_historical_precedents(user_id, group_id=group_id)[:5]
            
        # Join business contexts
        elif conv_type == 'business' and business_id:
            context["business"] = self.business_accounts.get(business_id, {})
            context["user_business_history"] = self.user_business_history.get((user_id, business_id), {})
            context["history"] = self.get_historical_precedents(user_id, business_id=business_id)[:5]
            
        # Join personal contexts
        elif conv_type == 'personal' and sender_user_id:
            context["sender"] = self.users.get(sender_user_id, {"user_id": sender_user_id})
            context["history"] = self.get_historical_precedents(user_id, sender_id=sender_user_id)[:5]
            
        # Add media path if applicable
        if message['media_type'] == 'image' and message['media_id']:
            context["media_path"] = self.images.get(message['media_id'], "")
        elif message['media_type'] == 'voice' and message['media_id']:
            context["media_path"] = self.voice_notes.get(message['media_id'], "")
            
        return context
