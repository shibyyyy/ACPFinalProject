CREATE TABLE word_history (
    id INT PRIMARY KEY,
    word_id INT NOT NULL,
    date_shown DATE NOT NULL,
    FOREIGN KEY (word_id) REFERENCES vocabulary(word_id)
);
