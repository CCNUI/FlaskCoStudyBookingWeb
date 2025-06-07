// /static/js/main.js (v5 - 稳定修复版)

document.addEventListener('DOMContentLoaded', function() {

    // --- 逻辑模块 1: 预约模态框 ---
    const modal = document.getElementById('reservationModal');
    if (modal) {
        const closeModalButton = modal.querySelector('.close-button');
        const reservationForm = modal.querySelector('#reservationForm');
        const deleteButton = modal.querySelector('#deleteButton');
        const scheduleGrid = document.querySelector('.schedule-grid');

        const modalDate = modal.querySelector('#modalDate');
        const modalTime = modal.querySelector('#modalTime');
        const modalCurrentUser = modal.querySelector('#modalCurrentUser');
        const modalDateInput = modal.querySelector('#modalDateInput');
        const modalTimeInput = modal.querySelector('#modalTimeInput');
        const nameInput = modal.querySelector('#nameInput');
        const modalMessage = modal.querySelector('#modalMessage');

        let activeCell = null;

        function openModal(cell) {
            activeCell = cell;
            const date = activeCell.dataset.date;
            const time = activeCell.dataset.time;
            const user = activeCell.dataset.user;

            modalDate.textContent = date;
            modalTime.textContent = time;
            modalCurrentUser.textContent = user || '无';
            nameInput.value = user;

            modalDateInput.value = date;
            modalTimeInput.value = time;

            modalMessage.style.display = 'none';
            modal.style.display = 'block';
            nameInput.focus();
        }

        function closeModal() {
            modal.style.display = 'none';
            activeCell = null;
        }

        if (scheduleGrid) {
            scheduleGrid.addEventListener('click', (e) => {
                if (e.target.tagName === 'TD' && e.target.dataset.date) {
                    openModal(e.target);
                }
            });
        }

        closeModalButton.onclick = closeModal;
        window.onclick = (event) => {
            if (event.target == modal) {
                closeModal();
            }
        };

        reservationForm.addEventListener('submit', (e) => {
            e.preventDefault();
            submitReservation({
                date: modalDateInput.value,
                time_slot: modalTimeInput.value,
                name: nameInput.value.trim()
            });
        });

        deleteButton.addEventListener('click', () => {
            if (!activeCell.dataset.user) {
                showModalMessage('该时段本来就无人预约。', 'info');
                return;
            }
            if (confirm(`确定要删除【${activeCell.dataset.user}】在【${modalDate.textContent} ${modalTime.textContent}】的预约吗？`)) {
                submitReservation({
                    date: modalDateInput.value,
                    time_slot: modalTimeInput.value,
                    name: ''
                });
            }
        });

        async function submitReservation(data) {
            try {
                const response = await fetch('/submit_reservation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data),
                });

                const result = await response.json();

                if (!response.ok) {
                    throw new Error(result.message || `HTTP error! status: ${response.status}`);
                }

                showModalMessage(result.message, result.status);

                if (result.status === 'success') {
                    if (activeCell) {
                        const newName = result.new_user || '';
                        activeCell.textContent = newName;
                        activeCell.dataset.user = newName;
                        activeCell.style.backgroundColor = newName ? '#cce5ff' : '';
                        activeCell.style.fontWeight = newName ? 'bold' : '';
                        activeCell.style.color = newName ? '#004085' : '';
                    }
                    setTimeout(closeModal, 1500);
                }
            } catch (error) {
                showModalMessage(error.message, 'error');
            }
        }

        function showModalMessage(message, type) {
            modalMessage.textContent = message;
            modalMessage.className = `modal-message ${type}`;
            modalMessage.style.display = 'block';
        }
    }

    // --- 逻辑模块 2: 管理员后台删除确认 ---
    const deleteForms = document.querySelectorAll('.js-delete-confirm-form');
    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault();
            const slotValueInput = form.querySelector('input[name="delete_timeslot_value"]');
            if (slotValueInput) {
                const slotValue = slotValueInput.value;
                const confirmation = confirm(`您确定要删除时间段 "${slotValue}" 吗？\n此操作将立即生效且无法撤销！`);
                if (confirmation) {
                    form.submit();
                }
            }
        });
    });

});