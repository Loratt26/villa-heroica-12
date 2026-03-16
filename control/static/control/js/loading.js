(function () {
  function extractFilename(contentDisposition, fallbackHref) {
    if (contentDisposition) {
      var utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match && utf8Match[1]) {
        return decodeURIComponent(utf8Match[1]);
      }

      var asciiMatch = contentDisposition.match(/filename=\"?([^\";]+)\"?/i);
      if (asciiMatch && asciiMatch[1]) {
        return asciiMatch[1];
      }
    }

    try {
      var url = new URL(fallbackHref, window.location.origin);
      var lastSegment = url.pathname.split('/').filter(Boolean).pop();
      return lastSegment || 'descarga.csv';
    } catch (error) {
      return 'descarga.csv';
    }
  }

  async function downloadLink(link) {
    activateLoading(link);

    try {
      var response = await fetch(link.href, {
        credentials: 'same-origin',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
      });

      if (!response.ok) {
        throw new Error('download-failed');
      }

      var blob = await response.blob();
      var filename = extractFilename(response.headers.get('Content-Disposition'), link.href);
      var objectUrl = window.URL.createObjectURL(blob);
      var anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(objectUrl);
      resetLoading(link);
    } catch (error) {
      resetLoading(link);
      window.location.href = link.href;
    }
  }

  function getOriginalLabel(element) {
    if (element.tagName === 'INPUT') {
      return element.value;
    }
    return element.innerHTML;
  }

  function setLabel(element, label) {
    if (element.tagName === 'INPUT') {
      element.value = label;
      return;
    }
    element.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' + label;
  }

  function activateLoading(element, text) {
    if (!element || element.dataset.loadingActive === 'true') {
      return;
    }

    element.dataset.loadingActive = 'true';
    element.dataset.originalLabel = getOriginalLabel(element);

    if (element.tagName === 'BUTTON' || element.tagName === 'INPUT') {
      element.disabled = true;
    }

    element.setAttribute('aria-disabled', 'true');
    element.classList.add('is-loading');

    var label = text || element.dataset.loadingText || 'Procesando...';
    setLabel(element, label);

    if (element.dataset.loadingReset) {
      window.setTimeout(function () {
        resetLoading(element);
      }, Number(element.dataset.loadingReset));
    }
  }

  function resetLoading(element) {
    if (!element || element.dataset.loadingActive !== 'true') {
      return;
    }

    if (element.dataset.originalLabel) {
      if (element.tagName === 'INPUT') {
        element.value = element.dataset.originalLabel;
      } else {
        element.innerHTML = element.dataset.originalLabel;
      }
    }

    if (element.tagName === 'BUTTON' || element.tagName === 'INPUT') {
      element.disabled = false;
    }

    element.removeAttribute('aria-disabled');
    element.classList.remove('is-loading');
    delete element.dataset.loadingActive;
    delete element.dataset.originalLabel;
  }

  document.addEventListener('submit', function (event) {
    if (event.defaultPrevented) {
      return;
    }

    var submitter = event.submitter;
    if (!submitter) {
      submitter = event.target.querySelector('button[type="submit"], input[type="submit"]');
    }
    if (submitter && !submitter.hasAttribute('data-no-loading')) {
      activateLoading(submitter);
    }
  });

  document.addEventListener('click', function (event) {
    var download = event.target.closest('a[data-download-link]');
    if (download && !download.hasAttribute('data-no-loading')) {
      event.preventDefault();
      downloadLink(download);
      return;
    }

    var link = event.target.closest('a[data-loading-link], a.btn, a.btn-main, a.btn-secondary, a.btn-back, a.link-secondary, a.nav-link');
    if (link && !link.hasAttribute('data-no-loading') && !link.hasAttribute('data-bs-toggle')) {
      if (link.target === '_blank') {
        activateLoading(link);
        window.setTimeout(function () {
          resetLoading(link);
        }, 900);
        return;
      }

      event.preventDefault();
      activateLoading(link);
      window.setTimeout(function () {
        window.location.href = link.href;
      }, 60);
      return;
    }

    var button = event.target.closest('button[data-loading-button]');
    if (button && !button.hasAttribute('data-no-loading')) {
      activateLoading(button);
    }
  });

  window.VHLoading = {
    activate: activateLoading,
    reset: resetLoading,
  };
})();
