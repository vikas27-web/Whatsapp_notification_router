import os
import sys
import csv
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# We import DataLoader from data_loader
try:
    from data_loader import DataLoader
except ImportError:
    from code.data_loader import DataLoader  # type: ignore

# Try to import LLM SDKs
genai = None
anthropic = None
openai = None

HAS_GEMINI = False
HAS_ANTHROPIC = False
HAS_OPENAI = False

try:
    import google.generativeai as genai  # type: ignore
    HAS_GEMINI = True
except ImportError:
    pass

try:
    import anthropic  # type: ignore
    HAS_ANTHROPIC = True
except ImportError:
    pass

try:
    import openai  # type: ignore
    HAS_OPENAI = True
except ImportError:
    pass


class MessageRouter:
    def __init__(self, dataset_dir):
        if not os.path.exists(dataset_dir):
            parent_dataset = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), dataset_dir)
            if os.path.exists(parent_dataset):
                dataset_dir = parent_dataset
        self.dataset_dir = dataset_dir
        self.dl = DataLoader(dataset_dir)
        self.media_cache = {}
        self.load_media_cache()

    def load_media_cache(self):
        cache_path = os.path.join(self.dataset_dir, 'media_cache.json')
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    self.media_cache = json.load(f)
                print(f"Loaded {len(self.media_cache)} items from media cache.")
            except Exception as e:
                print(f"Error loading media cache: {e}")
                self.media_cache = {}

    def get_media_content(self, message):
        media_type = message.get('media_type', '')
        media_id = message.get('media_id', '')
        
        if not media_type or not media_id:
            return ""
            
        cached = self.media_cache.get(media_id, {})
        if not cached:
            return f"[Media message of type {media_type} - Content unavailable]"
            
        if media_type == 'image':
            ocr = cached.get('ocr_text', '').strip()
            intent = cached.get('visual_intent', '').strip()
            return f"[Image OCR]: {ocr}\n[Image Intent]: {intent}"
        elif media_type == 'voice':
            transcription = cached.get('transcription', '').strip()
            return f"[Voice Transcription]: {transcription}"
            
        return f"[Media message of type {media_type}]"

    def rule_based_classify(self, message, ctx):
        """
        High-performance deterministic rule-based classifier that acts as:
        1. The deterministic safety override layer (FR3)
        2. The fallback processor if no API key is available or if LLM calls fail.
        """
        text = message.get('message_text', '') or ''
        media_content = self.get_media_content(message)
        combined_text = (text + "\n" + media_content).strip()
        lower_text = combined_text.lower()
        
        user_id = message.get('user_id', '')
        conv_type = message.get('conversation_type', '')
        sender_user_id = message.get('sender_user_id', '')
        forwarded_count = int(message.get('forwarded_count', 0) or 0)
        
        # Default fallback values
        action = "digest"
        message_type = "unknown"
        confidence = 0.91
        reason = "Routed via contextual rules."
        evidence_ids = "none"

        is_non_urgent_phrase = any(w in lower_text for w in ["nothing urgent", "not urgent", "talk tomorrow", "dont call now", "phone is charging", "no rush", "later", "whenever you get time"])
        
        urgent_keywords = [
            'urgent', 'emergency', 'valve', 'leak', 'plumber', 'water', 'electricity', 
            'outage', 'maintenance', 'now', 'immediate', 'child', 'parents', 'leaving', 
            'blocked', 'absent', 'sync', 'eod', 'incident', 'rollback', 'action items', 
            'online now', 'threshold', 'escalation', 'help', 'unwell', 'clinic',
            'passeport', 'passport', 'recuperer', 'récupérer', 'reception', 'réception', 'trouve', 'trouvé'
        ]
        has_urgent_keyword = any(k in lower_text for k in urgent_keywords) and not is_non_urgent_phrase

        # Gather relevant history precedents for evidence tracking
        history = ctx.get('history', [])
        evidence_list = []
        
        # 1. First priority: match history messages with text/topic overlap or media match
        for hist in history:
            h_text = hist.get('message_text', '') or ''
            if h_text and len(h_text) > 10 and (h_text[:25].lower() in lower_text or lower_text[:25] in h_text.lower()):
                evidence_list.append(hist['message_id'])
            elif hist.get('media_type') and hist.get('media_type') == message.get('media_type'):
                evidence_list.append(hist['message_id'])
                
        # 2. Fallback: if no text match but sender/group/business history exists, cite top precedent
        if not evidence_list and history:
            evidence_list.append(history[0]['message_id'])

        if evidence_list:
            # Deduplicate preserving order
            seen = set()
            unique_evidence = [x for x in evidence_list if not (x in seen or seen.add(x))]
            evidence_ids = ";".join(unique_evidence[:2])


        # ----------------------------------------------------
        # SAFETY OVERRIDES & SCAM/SPAM DETECTION (G4 & FR3)
        # ----------------------------------------------------
        
        # Check if it's a safety advisory (advisories are NOT scams)
        is_advisory = any(w in lower_text for w in ["never ask", "never share", "safety advisory", "avoid sharing", "keep safe", "awareness"])
        
        # Phishing / scam keywords from anyone
        scam_patterns = [
            'login code', 'verification code', 'otp', 'card details', 'verify immediately', 
            'account suspended', 'claim prize', 'lottery', 'reset your password', 
            'reply with the 6 digit', 'verify your identity', 'gift card', 
            'verification failed', 'reply with the otp', 'registry papers', 'registry paper', 
            'pay rs', 'token today', 'token payment', 'verify wallet'
        ]
        
        is_scam = False
        if not is_advisory and any(p in lower_text for p in scam_patterns):
            action = "mute"
            message_type = "scam"
            reason = "Muted high-risk security ask or unsolicited financial request."
            confidence = 0.95
            is_scam = True

        # Business domain mismatch (Spoofing / Phishing check)
        if not is_scam and conv_type == 'business':
            bus = ctx.get('business', {})
            off_domain = bus.get('official_domain', '')
            used_domain = bus.get('domain_used_by_sender', '')
            
            # Domain mismatch detected
            if off_domain and used_domain and off_domain.lower() != used_domain.lower():
                scam_keywords = ['pay', 'payment', 'link', 'click', 'verification', 'otp', 'code', 'card', 'bank', 'due', 'expire', 'update']
                if any(k in lower_text for k in scam_keywords):
                    action = "mute"
                    message_type = "scam"
                    reason = f"Muted due to official domain mismatch ({off_domain} vs {used_domain}) on payment/credential request."
                    confidence = 1.0
                    is_scam = True

        # High report count spam for businesses
        if not is_scam and conv_type == 'business':
            bus = ctx.get('business', {})
            try:
                reports = int(bus.get('user_reports_30d', 0) or 0)
            except ValueError:
                reports = 0
            if reports > 15:
                action = "mute"
                message_type = "spam"
                reason = f"Muted business account with high user report count (reports_30d = {reports})."
                confidence = 0.95
                is_scam = True

        # Forward count spam check
        if not is_scam and (forwarded_count > 5 or "fwd as received" in lower_text or "forward to family" in lower_text):
            action = "mute"
            if any(w in lower_text for w in ["good morning", "blessings", "stay positive", "keep smiling"]):
                message_type = "greeting"
                reason = "Muted forwarded greeting message with high forward count."
            else:
                message_type = "forward"
                reason = "Muted forwarded advice/information spam."
            confidence = 0.92
            is_scam = True

        # ----------------------------------------------------
        # @-MENTIONS MUTE BYPASS (FR3, G4)
        # ----------------------------------------------------
        is_mentioned = False
        if not is_scam and user_id and f"@{user_id}" in combined_text:
            is_mentioned = True
            action = "notify"
            if has_urgent_keyword:
                message_type = "urgent"
            else:
                message_type = "personal"
            reason = "Notified because the user was directly @-mentioned."
            confidence = 0.93

        # ----------------------------------------------------
        # CONTEXTUAL & RELATIONSHIP ROUTING (G2, G3, FR5)
        # ----------------------------------------------------
        if not is_scam and not is_mentioned:
            # Group routing
            if conv_type == 'group':
                group = ctx.get('group', {})
                group_type = group.get('group_type', '')
                membership = ctx.get('group_membership', {})
                is_muted = membership.get('group_muted_by_user', '0') == '1'
                
                sender_membership = ctx.get('sender_membership', {})
                is_admin = sender_membership.get('role', '') == 'admin'
                
                is_promo = any(w in lower_text for w in ['selling', 'kurta set', 'price', 'dm if interested', 'bought last', 'pickup near', 'sale', 'for sale', 'looking to buy'])
                
                if is_muted:
                    action = "mute"
                    if is_admin and has_urgent_keyword:
                        action = "notify"
                        message_type = "urgent"
                        reason = "Notified from muted group because a group admin sent a time-critical update."
                        confidence = 0.92
                    else:
                        if is_promo:
                            message_type = "promotion"
                        elif any(w in lower_text for w in ["good morning", "good night", "blessings"]):
                            message_type = "greeting"
                        elif forwarded_count > 0 or "fwd" in lower_text:
                            message_type = "forward"
                        else:
                            message_type = "event"
                        reason = "Muted message in user-muted group."
                        confidence = 0.92
                else:
                    # Non-muted groups
                    if group_type in ['school_group', 'society']:
                        if is_admin and has_urgent_keyword:
                            action = "notify"
                            if group_type == 'school_group':
                                message_type = "event"
                            else:
                                message_type = "urgent"
                            reason = f"Notified time-sensitive operational notice from {group_type} group admin."
                            confidence = 0.95
                        elif is_admin and any(w in lower_text for w in ['whenever you get time', 'no need to reply', 'till next', 'form is open']):
                            action = "digest"
                            message_type = "event"
                            reason = f"Notice from {group_type} group admin."
                            confidence = 0.92
                        elif is_admin:
                            action = "notify"
                            message_type = "event"
                            reason = f"Announcement from {group_type} group admin."
                            confidence = 0.92
                        else:
                            action = "digest"
                            message_type = "event"
                            reason = f"Routine update in {group_type} group."
                            confidence = 0.91
                            
                    elif group_type == 'coworker':
                        if has_urgent_keyword or is_admin:
                            action = "notify"
                            message_type = "urgent"
                            reason = "Notified coworker discussion."
                            confidence = 0.93
                        else:
                            action = "digest"
                            message_type = "business_update"
                            reason = "Routine coworker communication."
                            confidence = 0.91
                            
                    elif group_type in ['family', 'extended_family']:
                        if any(w in lower_text for w in ["good morning", "good night", "blessings"]):
                            action = "digest"
                            message_type = "greeting"
                            reason = "Family greeting sent to digest."
                            confidence = 0.92
                        elif forwarded_count > 0 or "fwd" in lower_text:
                            action = "digest"
                            message_type = "forward"
                            reason = "Forwarded message in family group."
                            confidence = 0.91
                        else:
                            if is_non_urgent_phrase:
                                action = "digest"
                                message_type = "personal"
                                reason = "Personal family communication sent to digest (non-urgent)."
                            elif has_urgent_keyword:
                                action = "notify"
                                message_type = "urgent"
                                reason = "Time-sensitive personal family communication."
                            else:
                                action = "notify"
                                message_type = "personal"
                                reason = "Personal family communication."
                            confidence = 0.93
                            
                    elif group_type == 'marketplace':
                        action = "digest"
                        message_type = "promotion"
                        reason = "Marketplace promotional message."
                        confidence = 0.92
                        
                    else:  # friends, alumni, book_club, local_food
                        if is_promo:
                            action = "digest"
                            message_type = "promotion"
                            reason = "Promotional message in interest group."
                        else:
                            action = "digest"
                            message_type = "personal"
                            reason = "Personal discussion in social group."
                        confidence = 0.91

            # Personal routing
            elif conv_type == 'personal':
                # Check engagement history
                engagement = False
                for h in history:
                    if h.get('replied') == '1' or h.get('opened') == '1':
                        engagement = True
                        break
                
                is_greeting = any(w in lower_text for w in ["good morning", "good night", "blessings", "hope today is"])
                is_forward = forwarded_count > 0 or "fwd" in lower_text
                
                if has_urgent_keyword:
                    action = "notify"
                    message_type = "urgent"
                    reason = "Direct personal message with time-critical request."
                    confidence = 0.94
                elif is_greeting:
                    action = "digest" if engagement else "mute"
                    message_type = "greeting"
                    reason = "Greeting message categorized based on relationship."
                    confidence = 0.91
                elif is_forward:
                    action = "digest" if engagement else "mute"
                    message_type = "forward"
                    reason = "Forwarded personal message categorized based on relationship."
                    confidence = 0.91
                elif engagement:
                    if is_non_urgent_phrase:
                        action = "digest"
                    else:
                        action = "notify"
                    message_type = "personal"
                    reason = "Direct personal message from active contact."
                    confidence = 0.93
                else:
                    if any(w in lower_text for w in ["by 6 pm", "by 5 pm", "gate 2", "collect"]) and not is_non_urgent_phrase:
                        action = "notify"
                        message_type = "urgent"
                        reason = "Direct personal message with time-sensitive pickup or request."
                        confidence = 0.92
                    elif is_non_urgent_phrase:
                        action = "digest"
                        message_type = "unknown"
                        reason = "Direct personal message from unfamiliar contact with low urgency."
                        confidence = 0.91
                    else:
                        action = "digest"
                        message_type = "unknown"
                        reason = "Direct personal message from unfamiliar contact."
                        confidence = 0.91

            # Business routing
            elif conv_type == 'business':
                biz_hist = ctx.get('user_business_history', {})
                allows_promotions = biz_hist.get('allows_promotions', '1') == '1'
                opted_out = biz_hist.get('promotions_opted_out_at', '') != ''
                why_knows = biz_hist.get('why_user_knows_account', '')
                
                has_active_relationship = why_knows in ['recent_grocery_delivery', 'recent_order', 'upcoming_clinic_appointment', 'active_bank_account']
                
                promo_keywords = ['off', 'discount', 'sale', 'coupon', 'cashback', 'promo', 'deal', 'offer', 'win', 'prize', 'trip', 'nights', 'itinerary', 'marketing', 'unsubscribe', 'stop to unsubscribe']
                is_promo = any(p in lower_text for p in promo_keywords) and not is_advisory
                
                if is_promo:
                    if not allows_promotions or opted_out or not why_knows:
                        action = "mute"
                    else:
                        action = "digest"
                    message_type = "promotion"
                    reason = "Promotional advertisement from business account."
                    confidence = 0.92
                else:
                    # Transactional updates
                    if has_active_relationship:
                        if any(w in lower_text for w in ['appointment', 'scheduled', 'clinic', 'visit', 'timing', 'prescription']):
                            action = "notify"
                            message_type = "event"
                            reason = "Healthcare appointment schedule update."
                        elif any(w in lower_text for w in ['pack', 'ship', 'deliver', 'hub', 'return', 'pickup', 'courier', 'out for delivery']):
                            action = "notify"
                            message_type = "business_update"
                            reason = "Transactional status update for active order/delivery."
                        else:
                            action = "notify"
                            message_type = "business_update"
                            reason = "Transactional alert from business."
                        confidence = 0.94
                    else:
                        action = "digest"
                        message_type = "business_update"
                        reason = "Status or transactional update from business account."
                        confidence = 0.91

        # ----------------------------------------------------
        # DND/QUIET HOURS ADJUSTMENT (Quiet-Hours parent, etc.)
        # ----------------------------------------------------
        user_info = ctx.get('user', {})
        dnd_window = user_info.get('do_not_disturb_window', '')
        if dnd_window and dnd_window != '':
            msg_time_str = message.get('created_at', '')
            if msg_time_str:
                try:
                    time_part = msg_time_str.split(' ')[-1]
                    h, m = map(int, time_part.split(':'))
                    msg_minutes = h * 60 + m
                    
                    dnd_start, dnd_end = dnd_window.split('-')
                    sh, sm = map(int, dnd_start.split(':'))
                    eh, em = map(int, dnd_end.split(':'))
                    start_minutes = sh * 60 + sm
                    end_minutes = eh * 60 + em
                    
                    in_dnd = False
                    if start_minutes > end_minutes:  # Spans midnight
                        if msg_minutes >= start_minutes or msg_minutes <= end_minutes:
                            in_dnd = True
                    else:
                        if start_minutes <= msg_minutes <= end_minutes:
                            in_dnd = True
                            
                    if in_dnd and action == "notify" and message_type != "urgent":
                        action = "digest"
                        reason = f"Downgraded to digest because message arrived during user's DND window ({dnd_window})."
                        confidence = 0.92
                except Exception as e:
                    pass

        return {
            "action": action,
            "message_type": message_type,
            "reason": reason,
            "confidence": confidence,
            "evidence_message_ids": evidence_ids
        }

    def call_gemini(self, prompt):
        if not HAS_GEMINI or genai is None:
            raise ImportError("google.generativeai package is not available.")
        if os.environ.get("GEMINI_API_KEY"):
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))  # type: ignore
        model = genai.GenerativeModel('gemini-3.5-flash-lite')  # type: ignore
        max_retries = 3
        for i in range(max_retries):
            try:
                response = model.generate_content(prompt)
                text = response.text.strip()
                # Find JSON block
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower() or "limit" in str(e).lower():
                    time.sleep(10 * (i+1))
                else:
                    raise e
        raise Exception("Failed to call Gemini API due to rate limits.")

    def call_anthropic(self, prompt):
        if not HAS_ANTHROPIC or anthropic is None:
            raise ImportError("anthropic package is not available.")
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))  # type: ignore
        max_retries = 3
        for i in range(max_retries):
            try:
                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    temperature=0.0,
                    system="You are a personal WhatsApp notification assistant. Output strictly valid JSON matching the requested schema.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                block = message.content[0]
                text = getattr(block, 'text', str(block)).strip()
                if "```json" in text:
                    text = text.split("```json")[1].split("```")[0].strip()
                elif "```" in text:
                    text = text.split("```")[1].split("```")[0].strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10 * (i+1))
                else:
                    raise e
        raise Exception("Failed to call Anthropic API due to rate limits.")

    def call_openai(self, prompt):
        if not HAS_OPENAI or openai is None:
            raise ImportError("openai package is not available.")
        client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))  # type: ignore
        max_retries = 3
        for i in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": "You are a personal WhatsApp notification assistant. Output strictly valid JSON matching the requested schema."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.0,
                    response_format={"type": "json_object"}
                )
                text = str(response.choices[0].message.content).strip()
                return json.loads(text)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(10 * (i+1))
                else:
                    raise e
        raise Exception("Failed to call OpenAI API due to rate limits.")

    def route_message(self, message):
        ctx = self.dl.get_message_context(message)
        
        # 1. Deterministic safety-override layer (FR3)
        # We always check safety rules first. If they force 'mute', we skip the LLM.
        safety_override = self.rule_based_classify(message, ctx)
        if safety_override['action'] == 'mute' and safety_override['message_type'] in ['scam', 'spam']:
            return safety_override

        # 2. Check if we have active LLM keys
        has_api_key = False
        provider = None
        
        if os.environ.get("GEMINI_API_KEY") and HAS_GEMINI:
            has_api_key = True
            provider = "gemini"
        elif os.environ.get("ANTHROPIC_API_KEY") and HAS_ANTHROPIC:
            has_api_key = True
            provider = "anthropic"
        elif os.environ.get("OPENAI_API_KEY") and HAS_OPENAI:
            has_api_key = True
            provider = "openai"

        if not has_api_key:
            # Fall back to our local rule-based classifier
            return safety_override

        # 3. Construct prompt
        text = message.get('message_text', '') or ''
        media_content = self.get_media_content(message)
        combined_text = (text + "\n" + media_content).strip()
        
        # Convert history precedents to string for prompt
        history_list = []
        for hist in ctx.get('history', []):
            hist_item = (
                f"- Message ID: {hist['message_id']} | Date: {hist['created_at']} | "
                f"Text: {hist['message_text']} | User Reactions: "
                f"Opened={hist['opened']}, Replied={hist['replied']}, "
                f"Dismissed={hist['dismissed']}, Reported={hist['reported']}, MutedAfter={hist['muted_after']}"
            )
            history_list.append(hist_item)
        history_str = "\n".join(history_list) if history_list else "No historical records."

        prompt = f"""
Incoming Message Details:
- Message ID: {message.get('message_id')}
- Conversation Type: {message.get('conversation_type')}
- Created At: {message.get('created_at')}
- Text / Content: {combined_text}
- Forwarded Count: {message.get('forwarded_count', '0')}

Receiving User Settings:
- User ID: {message.get('user_id')}
- DND Window: {ctx.get('user', {}).get('do_not_disturb_window', 'none')}
- 30-Day General Engagement: Opens={ctx.get('user', {}).get('messages_opened_30d')}, Replies={ctx.get('user', {}).get('messages_replied_30d')}, Dismissed={ctx.get('user', {}).get('notifications_dismissed_30d')}, Reported={ctx.get('user', {}).get('messages_reported_30d')}
- Notifications Fatigue (30-day loads): Average Daily Dismiss Rate={ctx.get('user_fatigue', {}).get('avg_dismiss_rate')}, Total Sent={ctx.get('user_fatigue', {}).get('total_sent_30d')}

Relationship Context:
- Group Info: {ctx.get('group', {})}
- Group Membership (User Role/Mute flag): {ctx.get('group_membership', {})}
- Business Account Info: {ctx.get('business', {})}
- User Business Relationship History: {ctx.get('user_business_history', {})}

Sender History Context (Precedents):
{history_str}

Evaluate carefully and route this message.
You must outputs a JSON object with this exact schema:
{{
  "action": "notify" | "digest" | "mute",
  "message_type": "personal" | "urgent" | "event" | "payment" | "business_update" | "promotion" | "greeting" | "forward" | "spam" | "scam" | "unknown",
  "reason": "One sentence human-readable reason referencing sender trust, quiet hours, user relationship, or risk signals.",
  "confidence": <float between 0.0 and 1.0>,
  "evidence_message_ids": "Semicolon-separated historical message IDs that match this content/sender patterns, or 'none' if no relevant history exists"
}}
"""

        res = None
        try:
            if provider == "gemini":
                res = self.call_gemini(prompt)
            elif provider == "anthropic":
                res = self.call_anthropic(prompt)
            elif provider == "openai":
                res = self.call_openai(prompt)
            
            # Validate output keys
            if res and isinstance(res, dict) and all(k in res for k in ['action', 'message_type', 'reason', 'confidence', 'evidence_message_ids']):
                # Double-check confidence type
                try:
                    res['confidence'] = float(res['confidence'])
                except (ValueError, TypeError):
                    res['confidence'] = 0.80
                return res
            else:
                return safety_override
        except Exception as e:
            # If API fails for any reason (e.g. rate limit), fall back to rule-based classifier
            print(f"LLM API call failed ({e}). Falling back to rule-based classifier.")
            return safety_override

    def process_all(self, input_csv, output_csv):
        print(f"Starting batch execution: {input_csv} -> {output_csv}...")
        
        # Load messages
        messages = self.dl._read_csv(input_csv)
        print(f"Loaded {len(messages)} messages to process.")
        
        results = []
        for i, msg in enumerate(messages):
            res = self.route_message(msg)
            results.append({
                "message_id": msg['message_id'],
                "action": res.get('action', 'digest'),
                "message_type": res.get('message_type', 'unknown'),
                "reason": res.get('reason', 'Routed via rules.'),
                "confidence": round(float(res.get('confidence', 0.91)), 2),
                "evidence_message_ids": res.get('evidence_message_ids', 'none')
            })
            if (i+1) % 10 == 0:
                print(f"Processed {i+1}/{len(messages)} messages...")

        # Write output
        output_path = os.path.join(self.dataset_dir, output_csv)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['message_id', 'action', 'message_type', 'reason', 'confidence', 'evidence_message_ids'])
            writer.writeheader()
            for r in results:
                writer.writerow(r)
                
        print(f"Batch execution completed! Results written to {output_path}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Message Notification Router")
    parser.add_argument('--input', type=str, default='messages.csv', help='Input messages file name inside dataset directory')
    parser.add_argument('--output', type=str, default='output.csv', help='Output file name inside dataset directory')
    parser.add_argument('--evaluate', action='store_true', help='Run evaluation against sample_messages.csv')
    args = parser.parse_args()

    router = MessageRouter('dataset')
    
    if args.evaluate:
        # Import evaluation helper dynamically
        try:
            from evaluation_helper import run_evaluation
        except ImportError:
            from code.evaluation_helper import run_evaluation  # type: ignore
        run_evaluation(router)
    else:
        router.process_all(args.input, args.output)
