from app import app, db

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("==================================================")
    print("  EduLearn LMS Platform is running!")
    print("  URL: http://127.0.0.1:5000")
    print("==================================================")
    app.run(debug=True, host='127.0.0.1', port=5000)
