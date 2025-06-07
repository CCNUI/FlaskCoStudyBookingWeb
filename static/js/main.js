// /static/js/main.js

// ... (文件之前的所有内容保持不变) ...

// --- 新增：管理员后台删除确认逻辑 ---
document.addEventListener('DOMContentLoaded', function() {
    const deleteForms = document.querySelectorAll('.js-delete-confirm-form');

    deleteForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            // 阻止表单立即提交
            event.preventDefault();

            const slotValue = form.querySelector('input[name="delete_timeslot_value"]').value;
            const confirmation = confirm(`您确定要删除时间段 "${slotValue}" 吗？\n此操作将立即生效且无法撤销！`);

            if (confirmation) {
                // 如果用户点击“确定”，则提交表单
                form.submit();
            }
            // 如果用户点击“取消”，则什么也不做
        });
    });
});