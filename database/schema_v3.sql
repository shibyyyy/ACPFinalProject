CREATE TABLE user_acc (
    user_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(200) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    date_created DATETIME,
    last_login DATETIME,
    pokemon_name VARCHAR(100),
    pokemon_id INT,
    profile_picture VARCHAR(200),
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    total_points INT DEFAULT 0,
    FOREIGN KEY (pokemon_id) REFERENCES pokemon(pokemon_id)
);
