// /static/js/main.js
document.addEventListener('DOMContentLoaded', function() {
    // --- 模态框逻辑 ---
    const modal = document.getElementById('reservationModal');
    const closeModalButton = document.querySelector('.close-button');
    const reservationForm = document.getElementById('reservationForm');
    const deleteButton = document.getElementById('deleteButton');
    const scheduleGrid = document.querySelector('.schedule-grid');

    // 模态框 DOM 元素
    const modalTitle = document.getElementById('modalTitle');
    const modalDate = document.getElementById('modalDate');
    const modalTime = document.getElementById('modalTime');
    const modalCurrentUser = document.getElementById('modalCurrentUser');
    const modalDateInput = document.getElementById('modalDateInput');
    const modalTimeInput = document.getElementById('modalTimeInput');
    const nameInput = document.getElementById('nameInput');
    const modalMessage = document.getElementById('modalMessage');

    let activeCell = null; // 用于存储当前被点击的单元格

    // 点击日历单元格时打开模态框
    if (scheduleGrid) {
        scheduleGrid.addEventListener('click', function(e) {
            if (e.target.tagName === 'TD' && e.target.dataset.date) {
                activeCell = e.target;
                const date = activeCell.dataset.date;
                const time = activeCell.dataset.time;
                const user = activeCell.dataset.user;

                // 填充模态框内容
                modalDate.textContent = date;
                modalTime.textContent = time;
                modalCurrentUser.textContent = user || '无';
                nameInput.value = user;

                // 填充表单隐藏字段
                modalDateInput.value = date;
                modalTimeInput.value = time;

                // 清除旧消息
                hideModalMessage();

                // 显示模态框
                modal.style.display = 'block';
                nameInput.focus();
            }
        });
    }

    // 关闭模态框
    function closeModal() {
        if (modal) {
            modal.style.display = 'none';
        }
        activeCell = null;
    }

    if (closeModalButton) {
        closeModalButton.onclick = closeModal;
    }

    window.onclick = function(event) {
        if (event.target == modal) {
            closeModal();
        }
    };

    // 显示模态框消息
    function showModalMessage(message, type) {
        modalMessage.textContent = message;
        modalMessage.className = `modal-message ${type}`;
        modalMessage.style.display = 'block';
    }

    // 隐藏模态框消息
    function hideModalMessage() {
        modalMessage.style.display = 'none';
    }

    // 提交预约表单 (创建/更新)
    if (reservationForm) {
        reservationForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const formData = {
                date: modalDateInput.value,
                time_slot: modalTimeInput.value,
                name: nameInput.value.trim()
            };
            submitReservation(formData);
        });
    }

    // 点击删除按钮
    if (deleteButton) {
        deleteButton.addEventListener('click', function() {
            if (!activeCell.dataset.user) {
                showModalMessage('该时段本来就无人预约。', 'info');
                return;
            }
            if (confirm(`确定要删除【${activeCell.dataset.user}】在【${modalDate.textContent} ${modalTime.textContent}】的预约吗？`)) {
                 const formData = {
                    date: modalDateInput.value,
                    time_slot: modalTimeInput.value,
                    name: '' // 发送空名字表示删除
                };
                submitReservation(formData);
            }
        });
    }

    // 统一的提交函数
    async function submitReservation(data) {
        try {
            const response = await fetch('/submit_reservation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();

            showModalMessage(result.message, result.status);

            if (result.status === 'success') {
                // 更新前端单元格
                if (activeCell) {
                    const newName = result.new_user || '';
                    activeCell.textContent = newName;
                    activeCell.dataset.user = newName;

                    // 更新单元格样式
                    if (newName) {
                        activeCell.style.backgroundColor = '#cce5ff';
                        activeCell.style.fontWeight = 'bold';
                        activeCell.style.color = '#004085';
                    } else {
                        activeCell.style.backgroundColor = '';
                        activeCell.style.fontWeight = '';
                        activeCell.style.color = '';
                    }
                }
                // 成功后延时关闭模态框
                setTimeout(() => {
                    closeModal();
                }, 1500);
            }

        } catch (error) {
            console.error('Fetch Error:', error);
            showModalMessage('请求失败，请检查网络或联系管理员。', 'error');
        }
    }
});