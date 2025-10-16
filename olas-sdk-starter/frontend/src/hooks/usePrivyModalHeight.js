import { useEffect, useState } from 'react';

export const usePrivyModalHeight = () => {
  const [modalHeight, setModalHeight] = useState(0);

  useEffect(() => {
    let timeoutId;

    const observer = new MutationObserver(() => {
      measureModalHeight();
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });

    const measureModalHeight = () => {
      const modal = document.querySelector('#privy-modal-content');

      if (modal) {
        setModalHeight(modal.clientHeight);
        return true;
      }

      return false;
    };

    const checkForModal = () => {
      if (!measureModalHeight()) {
        timeoutId = setTimeout(checkForModal, 100);
      } else {
        const modalContent = document.querySelector('#privy-modal-content');

        if (modalContent) {
          observer.observe(modalContent, {
            attributes: true,
          });

          modalContent.addEventListener('transitionrun', () => {
            measureModalHeight();
          });

          modalContent.addEventListener('transitionend', () => {
            measureModalHeight();
          });
        }
      }
    };

    checkForModal();

    return () => {
      if (observer) {
        observer.disconnect();
      }

      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, []);

  return modalHeight;
};
