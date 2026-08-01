import os
import zipfile
import shutil

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
code_dir = os.path.join(repo_root, 'code')
output_csv_src = os.path.join(repo_root, 'dataset', 'output.csv')
output_csv_dst = os.path.join(repo_root, 'output.csv')
zip_path = os.path.join(repo_root, 'code.zip')

# Copy to Downloads for easy user access
downloads_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
downloads_output = os.path.join(downloads_dir, 'output.csv')
downloads_zip = os.path.join(downloads_dir, 'code.zip')
downloads_log = os.path.join(downloads_dir, 'log.txt')
global_log = os.path.join(os.path.expanduser('~'), 'hackerrank_orchestrate_august26', 'log.txt')

# 1. Copy output.csv to repo root & Downloads
shutil.copyfile(output_csv_src, output_csv_dst)
shutil.copyfile(output_csv_src, downloads_output)
print(f"Copied dataset/output.csv -> {output_csv_dst} & {downloads_output}")

# 2. Create code.zip containing the code/ directory
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk(code_dir):
        if '__pycache__' in root:
            continue
        for file in files:
            file_path = os.path.join(root, file)
            arcname = os.path.relpath(file_path, repo_root)
            zipf.write(file_path, arcname)

shutil.copyfile(zip_path, downloads_zip)
print(f"Created submission archive -> {zip_path} & {downloads_zip}")

# 3. Copy log.txt to Downloads
if os.path.exists(global_log):
    shutil.copyfile(global_log, downloads_log)
    print(f"Copied log.txt -> {downloads_log}")
