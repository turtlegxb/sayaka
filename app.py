import os
import markdown
import codecs
from flask import Flask, render_template, abort

app = Flask(__name__)
# Get absolute path to the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTENT_DIR = os.path.join(BASE_DIR, 'content')

def get_post_metadata(filepath):
    """Extract metadata from a markdown file."""
    try:
        with codecs.open(filepath, mode="r", encoding="utf-8") as f:
            text = f.read()
        
        md = markdown.Markdown(extensions=['meta'])
        md.convert(text)
        meta = getattr(md, 'Meta', {})
        
        return {
            'title': meta.get('title', [os.path.basename(filepath)[:-3]])[0],
            'date': meta.get('date', [''])[0],
            'description': meta.get('description', [''])[0],
            'content': None # Placeholder for when we only need meta
        }
    except Exception:
        return None

def get_latest_date_in_dir(dir_path):
    """Recursively find the newest date in all markdown files within a directory."""
    latest_date = ""
    for root, _, filenames in os.walk(dir_path):
        for filename in filenames:
            if filename.endswith('.md'):
                meta = get_post_metadata(os.path.join(root, filename))
                if meta and meta['date'] > latest_date:
                    latest_date = meta['date']
    return latest_date

def get_content_items(rel_dir=""):
    """List items in a specific directory (non-recursive listing)."""
    target_path = os.path.join(CONTENT_DIR, rel_dir.strip('/'))
    if not os.path.exists(target_path) or not os.path.isdir(target_path):
        return []

    items = []
    # List current directory entries
    for entry in os.listdir(target_path):
        if entry.startswith('.'):
            continue
            
        full_path = os.path.join(target_path, entry)
        rel_item_path = os.path.join(rel_dir, entry).replace(os.sep, '/').strip('/')
        
        if os.path.isdir(full_path):
            # It's a folder
            latest_date = get_latest_date_in_dir(full_path)
            items.append({
                'id': rel_item_path,
                'title': entry,
                'type': 'folder',
                'date': latest_date,
                'description': f"Collection of documents in {entry}"
            })
        elif entry.endswith('.md'):
            # It's a file
            meta = get_post_metadata(full_path)
            if meta:
                items.append({
                    'id': rel_item_path[:-3], # remove .md
                    'title': meta['title'],
                    'type': 'file',
                    'date': meta['date'],
                    'description': meta['description']
                })

    # Sort: Folders first (type='folder' > type='file'), then date descending
    # Type 'folder' is larger than 'file' alphabetically, or we can use a custom key
    def sort_key(item):
        is_folder = (1 if item['type'] == 'folder' else 0)
        return (is_folder, item['date'], item['title'])

    return sorted(items, key=sort_key, reverse=True)

@app.route('/')
def index():
    items = get_content_items("")
    return render_template('index.html', files=items, current_path="")

@app.route('/<path:req_path>')
def catch_all(req_path):
    # Check if it's a directory
    dir_path = os.path.join(CONTENT_DIR, req_path)
    if os.path.isdir(dir_path):
        items = get_content_items(req_path)
        return render_template('index.html', files=items, current_path=req_path)
    
    # Check if it's a markdown file
    filepath = os.path.join(CONTENT_DIR, f"{req_path}.md")
    if not os.path.exists(filepath):
        abort(404)
        
    with codecs.open(filepath, mode="r", encoding="utf-8") as f:
        text = f.read()
        
    md = markdown.Markdown(extensions=[
        'meta', 
        'fenced_code', 
        'tables', 
        'codehilite'
    ])
    html_content = md.convert(text)
    meta = getattr(md, 'Meta', {})
    
    title = meta.get('title', [req_path.split('/')[-1]])[0]
    date = meta.get('date', [''])[0]
    description = meta.get('description', [''])[0]
    
    return render_template('post.html', 
                           title=title, 
                           date=date, 
                           description=description, 
                           content=html_content)

if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
