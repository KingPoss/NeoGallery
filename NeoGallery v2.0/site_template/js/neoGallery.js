function getRandomImages(imageArray, count) {
    let result = [];
    let taken = [];
    let len = imageArray.length;

    if (count > len) count = len;

    while (result.length < count) {
      let randomIndex = Math.floor(Math.random() * len);
      if (!taken.includes(randomIndex)) {
        taken.push(randomIndex);
        result.push(imageArray[randomIndex]);
      }
    }
    return result;
  }

  function createImages(galleryElement, tags) {
    fetch("json/media.json")
      .then(response => response.json())
      .then(data => {
        // legacy bare-array shape or current {config, posts}
        const galleryConfig = (data && !Array.isArray(data) && data.config) ? data.config : {};
        const originalImageArray = Array.isArray(data) ? data : (data.posts || []);
        const useThumbs = galleryConfig.useThumbnails !== false;
        const fullWidth = galleryConfig.fullImageWidth || null;

        var tagArray = tags.split(',');
        var imageArray = originalImageArray.filter(image => image.tags && image.tags.some(tag => tagArray.includes(tag)));

        if (tagArray.includes("random")) {
          imageArray = getRandomImages(imageArray, 6);
        }

        galleryElement.innerHTML = '';

        for (var i = 0; i < imageArray.length; i++) {
          var imgData = imageArray[i];

          var container = document.createElement('div');
          container.className = 'imageContainer';

          var img = document.createElement('img');
          img.src = useThumbs ? imgData.thumbnailSrc : imgData.fullSrc;
          if (!useThumbs && fullWidth) img.style.width = fullWidth + 'px';

          // closure so each click handler sees its own imgData
          (function(imgData) {
            img.onclick = function() {
              var modal = document.getElementById("myModal");
              var modalImg = document.getElementById("img01");
              var titleText = document.getElementById("title");
              var captionText = document.getElementById("caption");
              var loadingPlaceholder = document.getElementById("loadingPlaceholder");

              modal.style.display = "block";
              if (loadingPlaceholder) {
                loadingPlaceholder.style.display = "block";
                modalImg.style.display = "none";
              }
              document.body.style.overflow = "hidden";
              modalImg.src = imgData.fullSrc;
              titleText.innerHTML = imgData.title;
              captionText.innerHTML = imgData.description;

              var newImage = new Image();
              newImage.src = imgData.fullSrc;

              newImage.onload = function() {
                  if (loadingPlaceholder) loadingPlaceholder.style.display = "none";
                  modalImg.src = this.src;
                  modalImg.style.display = "block";
              };

              newImage.onerror = function() {
                  if (loadingPlaceholder) loadingPlaceholder.style.display = "none";
                  console.error('Failed to load image:', this.src);
              };
            };
          })(imgData);

          var title = document.createElement('p');
          title.textContent = imgData.title;

          container.appendChild(img);
          container.appendChild(title);
          galleryElement.appendChild(container);
        }

        // wire modal close handlers once
        if (!window.modalHandlersInitialized) {
          var modal = document.getElementById("myModal");
          var span = document.getElementsByClassName("close")[0];

          if (span) {
            span.onclick = function() {
              modal.style.display = "none";
              document.body.style.overflow = "auto";
            }
          }

          window.onclick = function(event) {
            if (event.target == modal) {
              modal.style.display = "none";
              document.body.style.overflow = "auto";
            }
          }
          window.modalHandlersInitialized = true;
        }
      })
      .catch(error => console.error('Error fetching images:', error));
  }

  window.onload = function() {
    document.querySelectorAll('.gallery').forEach(gallery => {
        const tags = gallery.dataset.tag;
        createImages(gallery, tags);
    });
};

  // reshuffle button only exists on random galleries
  var reshuffleEl = document.getElementById('reshuffle');
  if (reshuffleEl) {
    reshuffleEl.onclick = function() {
      const allGallery = document.querySelector('.gallery[data-tag="random"]');
      if (allGallery) createImages(allGallery, 'random');
    };
  }
