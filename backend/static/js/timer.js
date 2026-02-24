let time = 300; // 5 minutes

function startTimer() {

    const timerDisplay = document.getElementById("timer");

    const interval = setInterval(() => {

        let minutes = Math.floor(time / 60);
        let seconds = time % 60;

        timerDisplay.innerHTML =
            `Time Left: ${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;

        time--;

        if (time < 0) {
            clearInterval(interval);
            alert("⏳ Time Up! Auto Submitting Exam...");
            document.getElementById("examForm").submit();
        }

    }, 1000);
}

window.onload = startTimer;
