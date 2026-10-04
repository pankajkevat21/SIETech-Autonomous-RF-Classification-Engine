document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById("upload-form");
    if(form) {
        form.addEventListener("submit", function() {
            document.getElementById("submit-btn").disabled = true;
            document.getElementById("loading").style.display = "block";
        });
    }
});
