CREATE TABLE pokemon (
    pokemon_id INT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    url VARCHAR(200),
    min_points_required INT DEFAULT 0,
    rarity VARCHAR(20) DEFAULT 'common',
    family_id INT NOT NULL
);
