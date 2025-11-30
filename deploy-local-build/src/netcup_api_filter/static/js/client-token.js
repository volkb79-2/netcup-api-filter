
(function () {
    const script = document.currentScript || document.querySelector("script[data-generate-url][src*='client-token.js']");
    const defaultGenerateUrl = script && script.dataset.generateUrl ? script.dataset.generateUrl : '';

    const createButton = (input) => {
        const formGroup = input.closest('.form-group');
        if (!formGroup) {
            return null;
        }

        const label = formGroup.querySelector('label[for="client_id"]');
        const wrapper = document.createElement('div');
        wrapper.className = 'token-label-row';

        if (label && label.parentNode) {
            label.parentNode.insertBefore(wrapper, label);
            wrapper.appendChild(label);
        } else {
            formGroup.insertBefore(wrapper, formGroup.firstChild);
        }

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-important token-generate-btn';
        button.textContent = 'Generate ID';
        if (defaultGenerateUrl) {
            button.dataset.generateUrl = defaultGenerateUrl;
        }
        wrapper.appendChild(button);
        return button;
    };

    const init = () => {
        const input = document.getElementById('client_id');
        if (!input) {
            return;
        }

        let button = document.querySelector('.token-generate-btn');
        if (!button) {
            button = createButton(input);
        } else if (!button.dataset.generateUrl && defaultGenerateUrl) {
            button.dataset.generateUrl = defaultGenerateUrl;
        }

        if (!button) {
            return;
        }

        const endpoint = button.dataset.generateUrl || defaultGenerateUrl;
        if (!endpoint) {
            console.warn('client-token.js did not receive a token generation endpoint');
            return;
        }

        if (button.dataset.tokenHandlerAttached === '1') {
            return;
        }
        button.dataset.tokenHandlerAttached = '1';

        async function generateToken() {
            button.disabled = true;
            const originalLabel = button.textContent || 'Generate ID';
            button.textContent = 'Generating...';

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (!response.ok) {
                    throw new Error('Request failed');
                }

                const payload = await response.json();
                if (!payload.token) {
                    throw new Error('Invalid payload');
                }

                input.value = payload.token;
                input.setAttribute('value', payload.token);
                input.dispatchEvent(new Event('input', { bubbles: true }));
            } catch (error) {
                alert('Unable to generate a token automatically. Please try again.');
                console.error(error);
            } finally {
                button.disabled = false;
                button.textContent = originalLabel;
            }
        }

        button.addEventListener('click', generateToken);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
})();
