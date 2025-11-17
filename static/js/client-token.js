(function () {
    const script = document.currentScript;
    if (!script) {
        return;
    }

    const generateUrl = script.dataset.generateUrl;
    if (!generateUrl) {
        return;
    }

    const init = () => {
        const input = document.getElementById('client_id');
        if (!input) {
            return;
        }

        const formGroup = input.closest('.form-group');
        if (!formGroup) {
            return;
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
        button.className = 'btn btn-outline-light token-generate-btn';
        button.textContent = 'Create Token';
        wrapper.appendChild(button);

        async function generateToken() {
            button.disabled = true;
            const originalLabel = 'Create Token';
            button.textContent = 'Generating...';

            try {
                const response = await fetch(generateUrl, {
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
