CREATE TABLE user_achievement (
    user_achievement_id INT PRIMARY KEY,
    user_id INT NOT NULL,
    achievement_id INT NOT NULL,
    current_progress INT DEFAULT 0,
    date_earned DATETIME,
    FOREIGN KEY (user_id) REFERENCES user_acc(user_id),
    FOREIGN KEY (achievement_id) REFERENCES achievement(achievement_id)
);
