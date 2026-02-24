import database as db

DB = "proctoring.db"

# Load all questions for an exam code
def get_exam_questions(exam_code):
    conn = db.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT * FROM questions WHERE exam_code = ?", (exam_code,))
    questions = cur.fetchall()

    conn.close()
    return questions


# Score calculation
def calculate_score(form_data):
    conn = db.connect(DB)
    cur = conn.cursor()

    score = 0

    for qid in form_data:
        user_answer = form_data[qid]

        cur.execute("SELECT answer FROM questions WHERE id=?", (qid,))
        correct = cur.fetchone()

        if correct and correct[0] == user_answer:
            score += 1

    conn.close()
    return score
