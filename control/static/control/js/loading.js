(function () {
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
