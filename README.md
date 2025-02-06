# NeoGallery - A gallery management solution for Neocities

NeoGallery is a Flask-based application that manages image uploads, thumbnail generation, tagging, and synchronizing these assets to your neocities site via the neocities API. It provides a web interface for uploading new images, associating tags, managing tags, and editing or deleting existing media. It comes with a gallery template that is repsonsive and works well on both desktop and mobile.
![NeoGallery Example Photo](https://i.imgur.com/mjuKiro.png)
### Key Features

1.  **Image Uploading & Thumbnail Generation**
Automatically resizes images (including animated GIFs) to create thumbnails using Pillow (PIL).
    
2.  **Tag Management**
Create, edit, and delete tags. Automatically inject links to tag pages in a gallery directory page.
    
3.  **Gallery Entries Management**
Upload, edit tags, and delete gallery entries from the web interface.
    
4.  **Gallery Display**
Display gallery entries in lists based on the provided tags. Responsive layout lets it look decent even on mobile devices!
    
### Prerequisites

1. (Skip to step 3 if you are running the executable ver) A patched version of `python-neocities`. The current version has a bug in the delete function on line #79 in `neocities.py` where it uses the get method instead of post, as the neocities API requires. It hasn’t been updated in about 6 years, so I took the liberty of patching it and hosting a copy of it in this repository. Use `python setup.py install` in the `python-neocities-delete-fix` folder to install.

2. All libraries listed in `requirements.txt`, use `pip install -r requirements.txt`

3. Your Neocities API key, found under ‘manage site settings’ on Neocities. Generate one, and place in the .env file on the `NEOCITIES_API_KEY` line.

4. By default, your site structure must be the following. You can upload all folders in the `NEOCITIES FILE STRUCTURE` folder for ease of use.This can be can all be changed in the .env if you desire:
```
│   NeoGallery.html
├───assets
│   │   hourglass.gif
│   │
│   ├───media
│   └───thumbnails
├───css
│       gallery.css
│
├───js
│       neoGallery.js
│
└───json
        media.json
        tags.json
```

### How to use

1. Launch `NeoGallery.py` or `NeoGallery.exe`, a window should open in your default browser to `https://127.0.0.1:5000` by default, but if not, head to it manually.
2. Upload away!

