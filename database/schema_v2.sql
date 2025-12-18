CREATE TABLE achievement (
    achievement_id INT PRIMARY KEY,
    pokemon_id INT NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    points_reward INT DEFAULT 0,
    requirement INT DEFAULT 0,
    FOREIGN KEY (pokemon_id) REFERENCES pokemon(pokemon_id) 
);
