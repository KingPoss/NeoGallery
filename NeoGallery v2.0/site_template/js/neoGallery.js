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
      .then(originalImageArray => {
        // Convert the tags string into an array of tags
        var tagArray = tags.split(',');

        // Filter images that include at least one of the tags
        var imageArray = originalImageArray.filter(image => image.tags && image.tags.some(tag => tagArray.includes(tag)));

        // For galleries with "random" tag, show only 6 random images
        if (tagArray.includes("random")) {
          imageArray = getRandomImages(imageArray, 6);
        }

        // Clear the specific gallery and hide its loader
        galleryElement.innerHTML = '';
        const loader = galleryElement.querySelector('.gallery-loader');
        if (loader) loader.style.display = 'none';

        for (var i = 0; i < imageArray.length; i++) {
          var imgData = imageArray[i];

          var container = document.createElement('div');
          container.className = 'imageContainer';

          var img = document.createElement('img');
          img.src = imgData.thumbnailSrc;

          // Closure to preserve imgData context
          (function(imgData) {
            img.onclick = function() {
              var modal = document.getElementById("myModal");
              var modalImg = document.getElementById("img01");
              var titleText = document.getElementById("title");
              var captionText = document.getElementById("caption");
              var loadingPlaceholder = document.getElementById("loadingPlaceholder");

              modal.style.display = "block";
              loadingPlaceholder.style.display = "block";
              modalImg.style.display = "none";
              document.body.style.overflow = "hidden";
              modalImg.src = imgData.fullSrc;
              titleText.innerHTML = imgData.title;
              captionText.innerHTML = imgData.description;

              // Load the image
              var newImage = new Image();
              newImage.src = imgData.fullSrc;

              newImage.onload = function() {
                  loadingPlaceholder.style.display = "none";
                  modalImg.src = this.src;
                  modalImg.style.display = "block";
              };

              newImage.onerror = function() {
                  loadingPlaceholder.style.display = "none";
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

        // Modal close handlers (only needs to be set up once)
        if (!window.modalHandlersInitialized) {
          var modal = document.getElementById("myModal");
          var span = document.getElementsByClassName("close")[0];

          span.onclick = function() { 
            modal.style.display = "none";
            document.body.style.overflow = "auto";
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
  
  // Reshuffle only the 'random' gallery
  document.getElementById('reshuffle').onclick = function() {
    const allGallery = document.querySelector('.gallery[data-tag="random"]');
    createImages(allGallery, 'random');
  };