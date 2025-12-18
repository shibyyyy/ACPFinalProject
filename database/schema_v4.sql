CREATE TABLE vocabulary (
    word_id INT PRIMARY KEY,
    word VARCHAR(100) NOT NULL,
    definition TEXT,
    example_sentence TEXT,
    category VARCHAR(50),
    points_value INT DEFAULT 10,
    is_word_of_day BOOLEAN DEFAULT FALSE
);
