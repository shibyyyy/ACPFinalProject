CREATE TABLE notification (
    notification_id INT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at DATETIME,
    data TEXT,
    FOREIGN KEY (user_id) REFERENCES user_acc(user_id)
);
