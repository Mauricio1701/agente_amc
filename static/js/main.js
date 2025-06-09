document.addEventListener('DOMContentLoaded', function() {
    // Configuración del micrófono (para futura implementación)
    const voiceBtn = document.getElementById('voice-btn');
    if (voiceBtn) {
        voiceBtn.addEventListener('click', function() {
            // Implementar función de grabación de voz
            alert('La función de voz estará disponible próximamente.');
        });
    }
    
    // Confirmaciones para acciones destructivas
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm') || '¿Estás seguro?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });
    
    // Tooltip initialization (si se usa Bootstrap)
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    const tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Mostrar/ocultar elementos basados en clases
    const togglers = document.querySelectorAll('[data-toggle]');
    togglers.forEach(toggler => {
        toggler.addEventListener('click', function() {
            const target = document.querySelector(this.getAttribute('data-toggle'));
            if (target) {
                target.classList.toggle('d-none');
            }
        });
    });
});

// Función para formatear fechas
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleString();
}

// Función para truncar texto
function truncateText(text, maxLength = 100) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Funciones para hacer peticiones AJAX
function ajaxGet(url, callback) {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', url);
    xhr.onload = function() {
        if (xhr.status === 200) {
            callback(null, JSON.parse(xhr.responseText));
        } else {
            callback(xhr.statusText);
        }
    };
    xhr.onerror = function() {
        callback('Error de red');
    };
    xhr.send();
}

function ajaxPost(url, data, callback) {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
        if (xhr.status === 200) {
            callback(null, JSON.parse(xhr.responseText));
        } else {
            callback(xhr.statusText);
        }
    };
    xhr.onerror = function() {
        callback('Error de red');
    };
    xhr.send(JSON.stringify(data));
}