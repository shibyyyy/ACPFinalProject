CREATE TABLE user_words (
    user_word_id INT PRIMARY KEY,
    user_id INT NOT NULL,
    word_id INT NOT NULL,
    date_learned DATETIME,
    FOREIGN KEY (user_id) REFERENCES user_acc(user_id),
    FOREIGN KEY (word_id) REFERENCES vocabulary(word_id)
);
