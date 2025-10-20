docker exec -it $(docker ps -qf name=postgres) psql -U postgres -d postgres -c "
CREATE SCHEMA IF NOT EXISTS inventory;
CREATE TABLE IF NOT EXISTS inventory.orders(
  id SERIAL PRIMARY KEY,
  customer VARCHAR(100),
  amount NUMERIC(10,2),
  created_at TIMESTAMPTZ DEFAULT now()
);
INSERT INTO inventory.orders(customer, amount) VALUES
('Alice', 10.50), ('Bob', 23.99);
"
