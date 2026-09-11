import os
import re

def clean_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_len = len(content)

    if filepath.endswith(('.java', '.cpp', '.h')):
        # Remove multi-line comments /* ... */
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments // ...
        content = re.sub(r'//.*', '', content)
    elif filepath.endswith('.py'):
        # Remove single-line comments # ...
        content = re.sub(r'#.*', '', content)

    # Remove empty lines left behind by comment removal
    # A line that is now empty or just whitespace
    lines = content.splitlines()
    cleaned_lines = [line for line in lines if line.strip() != '']
    
    # Rejoin with newlines
    new_content = '\n'.join(cleaned_lines) + '\n'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
        
    return original_len != len(new_content)

def main():
    dirs = ['java/src', 'cpp/src', 'python']
    files_changed = 0
    for d in dirs:
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith(('.java', '.cpp', '.h', '.py')):
                    filepath = os.path.join(root, file)
                    if clean_file(filepath):
                        files_changed += 1
                        print(f"Cleaned {filepath}")
    
    print(f"Total files cleaned: {files_changed}")

if __name__ == '__main__':
    main()
