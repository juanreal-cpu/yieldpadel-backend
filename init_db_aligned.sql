-- ==============================================================================
-- YIELDPADEL & CAPITAL PÁDEL CLUB (MALOKA) - SCHEMA DE BASE DE DATOS ALINEADO
-- Compatibilidad total e idempotente para PostgreSQL / Supabase
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------------------------------------
-- 1. TABLA: clubs
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS clubs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(150) NOT NULL,
    slug VARCHAR(100),
    address TEXT,
    phone_contact VARCHAR(50),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Asegurar columnas y defaults si la tabla ya existía
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS slug VARCHAR(100);
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS phone_contact VARCHAR(50);
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE clubs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE clubs ALTER COLUMN created_at SET DEFAULT NOW();

-- ------------------------------------------------------------------------------
-- 2. TABLA: courts
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS courts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    club_id UUID REFERENCES clubs(id) ON DELETE SET NULL,
    court_number INTEGER,
    name VARCHAR(100) NOT NULL,
    sport_type VARCHAR(50) NOT NULL DEFAULT 'PADEL',
    max_capacity INTEGER NOT NULL DEFAULT 4,
    is_indoor BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE courts ADD COLUMN IF NOT EXISTS club_id UUID;
ALTER TABLE courts ADD COLUMN IF NOT EXISTS court_number INTEGER;
ALTER TABLE courts ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) NOT NULL DEFAULT 'PADEL';
ALTER TABLE courts ADD COLUMN IF NOT EXISTS max_capacity INTEGER NOT NULL DEFAULT 4;
ALTER TABLE courts ADD COLUMN IF NOT EXISTS is_indoor BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE courts ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE courts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE courts ALTER COLUMN created_at SET DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_courts_sport_type ON courts(sport_type);
CREATE INDEX IF NOT EXISTS idx_courts_court_number ON courts(court_number);

-- ------------------------------------------------------------------------------
-- 3. TABLA: membership_plans
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS membership_plans (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    start_time TIME WITHOUT TIME ZONE NOT NULL DEFAULT '06:00:00',
    end_time TIME WITHOUT TIME ZONE NOT NULL DEFAULT '23:59:00',
    max_daily_hours DOUBLE PRECISION NOT NULL DEFAULT 1.5,
    includes_academy_classes BOOLEAN NOT NULL DEFAULT FALSE,
    monthly_classes_count INTEGER NOT NULL DEFAULT 0,
    includes_beverage_perk BOOLEAN NOT NULL DEFAULT FALSE,
    americano_discount_pct INTEGER NOT NULL DEFAULT 0,
    monthly_price_cop INTEGER NOT NULL DEFAULT 0,
    badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO',
    card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS start_time TIME WITHOUT TIME ZONE NOT NULL DEFAULT '06:00:00';
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS end_time TIME WITHOUT TIME ZONE NOT NULL DEFAULT '23:59:00';
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS max_daily_hours DOUBLE PRECISION NOT NULL DEFAULT 1.5;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS includes_academy_classes BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS monthly_classes_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS includes_beverage_perk BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS americano_discount_pct INTEGER NOT NULL DEFAULT 0;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS monthly_price_cop INTEGER NOT NULL DEFAULT 0;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS badge_label VARCHAR(50) DEFAULT 'PLAN SOCIO';
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS card_gradient VARCHAR(100) DEFAULT 'from-slate-800 to-indigo-900';
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE membership_plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE membership_plans ALTER COLUMN created_at SET DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_membership_plans_name ON membership_plans(name);

-- ------------------------------------------------------------------------------
-- 4. TABLA: customers (Players / Clientes)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(50) NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT '4ta',
    client_type VARCHAR(50) NOT NULL DEFAULT 'Estándar',
    membership_tier VARCHAR(50) NOT NULL DEFAULT 'ESTANDAR',
    notes VARCHAR(500),
    gender VARCHAR(20),
    preferred_music VARCHAR(100),
    preferred_play_time VARCHAR(100),
    membership_plan_id INTEGER REFERENCES membership_plans(id) ON DELETE SET NULL,
    membership_start_date DATE,
    membership_end_date DATE,
    academy_classes_used INTEGER NOT NULL DEFAULT 0,
    is_minor BOOLEAN NOT NULL DEFAULT FALSE,
    birth_date DATE,
    guardian_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    guardian_relationship VARCHAR(50),
    total_bookings_completed INTEGER NOT NULL DEFAULT 0,
    is_first_visit BOOLEAN NOT NULL DEFAULT TRUE,
    onboarding_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    ranking_points INTEGER NOT NULL DEFAULT 0,
    titles_count INTEGER NOT NULL DEFAULT 0,
    category_wins INTEGER NOT NULL DEFAULT 0,
    consecutive_wins INTEGER NOT NULL DEFAULT 0,
    promotion_recommended BOOLEAN NOT NULL DEFAULT FALSE,
    recommended_category VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE customers ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT '4ta';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS client_type VARCHAR(50) NOT NULL DEFAULT 'Estándar';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_tier VARCHAR(50) NOT NULL DEFAULT 'ESTANDAR';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes VARCHAR(500);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS gender VARCHAR(20);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS preferred_music VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS preferred_play_time VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_plan_id INTEGER REFERENCES membership_plans(id) ON DELETE SET NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_start_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS membership_end_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS academy_classes_used INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_minor BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS birth_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS guardian_id INTEGER REFERENCES customers(id) ON DELETE SET NULL;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS guardian_relationship VARCHAR(50);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS total_bookings_completed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS is_first_visit BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS onboarding_status VARCHAR(50) NOT NULL DEFAULT 'PENDING';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS ranking_points INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS titles_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS category_wins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS consecutive_wins INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS promotion_recommended BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS recommended_category VARCHAR(50);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW();
ALTER TABLE customers ALTER COLUMN created_at SET DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);
CREATE INDEX IF NOT EXISTS idx_customers_membership_plan_id ON customers(membership_plan_id);
CREATE INDEX IF NOT EXISTS idx_customers_guardian_id ON customers(guardian_id);

-- ------------------------------------------------------------------------------
-- 5. TABLA: time_slots
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS time_slots (
    id SERIAL PRIMARY KEY,
    court_id UUID NOT NULL REFERENCES courts(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    start_time TIME WITHOUT TIME ZONE NOT NULL,
    end_time TIME WITHOUT TIME ZONE NOT NULL,
    total_price NUMERIC(10, 2) NOT NULL,
    mode VARCHAR(50) NOT NULL DEFAULT 'FULL_COURT',
    capacity INTEGER NOT NULL DEFAULT 4,
    booked_spots INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'AVAILABLE',
    players_names JSON NOT NULL DEFAULT '[]'::json,
    category VARCHAR(50) NOT NULL DEFAULT '4ta',
    closed_at TIMESTAMP WITH TIME ZONE,
    slot_type VARCHAR(50) NOT NULL DEFAULT 'MATCH',
    instructor_name VARCHAR(100),
    is_promo BOOLEAN NOT NULL DEFAULT FALSE,
    tournament_type VARCHAR(50),
    prize_pool NUMERIC(10, 2),
    tournament_name VARCHAR(150),
    winners_names VARCHAR(255),
    runner_up_names VARCHAR(255),
    is_finished BOOLEAN NOT NULL DEFAULT FALSE,
    sport_type VARCHAR(50) NOT NULL DEFAULT 'PADEL',
    club_id INTEGER DEFAULT 1,
    price_total_cop NUMERIC(10, 2),
    price_per_player_cop NUMERIC(10, 2),
    price NUMERIC(10, 2)
);

ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS mode VARCHAR(50) NOT NULL DEFAULT 'FULL_COURT';
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS capacity INTEGER NOT NULL DEFAULT 4;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS booked_spots INTEGER NOT NULL DEFAULT 0;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'AVAILABLE';
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS players_names JSON NOT NULL DEFAULT '[]'::json;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS category VARCHAR(50) NOT NULL DEFAULT '4ta';
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS slot_type VARCHAR(50) NOT NULL DEFAULT 'MATCH';
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS instructor_name VARCHAR(100);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS is_promo BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS tournament_type VARCHAR(50);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS prize_pool NUMERIC(10, 2);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS tournament_name VARCHAR(150);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS winners_names VARCHAR(255);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS runner_up_names VARCHAR(255);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS is_finished BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS sport_type VARCHAR(50) NOT NULL DEFAULT 'PADEL';
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS club_id INTEGER DEFAULT 1;
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price_total_cop NUMERIC(10, 2);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price_per_player_cop NUMERIC(10, 2);
ALTER TABLE time_slots ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2);

CREATE INDEX IF NOT EXISTS idx_time_slots_court_id ON time_slots(court_id);
CREATE INDEX IF NOT EXISTS idx_time_slots_date ON time_slots(date);
CREATE INDEX IF NOT EXISTS idx_time_slots_status ON time_slots(status);
CREATE INDEX IF NOT EXISTS idx_time_slots_sport_type ON time_slots(sport_type);
CREATE INDEX IF NOT EXISTS idx_time_slots_court_date_time ON time_slots(court_id, date, start_time);

-- ------------------------------------------------------------------------------
-- 6. TABLA: slot_holds
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slot_holds (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES time_slots(id) ON DELETE CASCADE,
    customer_phone VARCHAR(50) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    spots_held INTEGER NOT NULL DEFAULT 1,
    amount_to_pay NUMERIC(10, 2) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    payment_reference VARCHAR(100) UNIQUE NOT NULL,
    client_tier VARCHAR(50) NOT NULL DEFAULT 'STANDARD',
    payment_status VARCHAR(50) NOT NULL DEFAULT 'PAID'
);

ALTER TABLE slot_holds ADD COLUMN IF NOT EXISTS client_tier VARCHAR(50) NOT NULL DEFAULT 'STANDARD';
ALTER TABLE slot_holds ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'PAID';

CREATE INDEX IF NOT EXISTS idx_slot_holds_slot_id ON slot_holds(slot_id);
CREATE INDEX IF NOT EXISTS idx_slot_holds_expires_at ON slot_holds(expires_at);
CREATE INDEX IF NOT EXISTS idx_slot_holds_payment_ref ON slot_holds(payment_reference);

-- ------------------------------------------------------------------------------
-- 7. TABLA: yield_bookings
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS yield_bookings (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES time_slots(id) ON DELETE CASCADE,
    customer_phone VARCHAR(50) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    spots_booked INTEGER NOT NULL,
    amount_paid NUMERIC(10, 2) NOT NULL,
    payment_reference VARCHAR(100) NOT NULL,
    transaction_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    client_tier VARCHAR(50) NOT NULL DEFAULT 'STANDARD',
    payment_status VARCHAR(50) NOT NULL DEFAULT 'PAID'
);

ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS client_tier VARCHAR(50) NOT NULL DEFAULT 'STANDARD';
ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS payment_status VARCHAR(50) NOT NULL DEFAULT 'PAID';
ALTER TABLE yield_bookings ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_yield_bookings_slot_id ON yield_bookings(slot_id);
CREATE INDEX IF NOT EXISTS idx_yield_bookings_payment_ref ON yield_bookings(payment_reference);

-- ------------------------------------------------------------------------------
-- 8. TABLA: academy_classes
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academy_classes (
    id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    level VARCHAR(50) NOT NULL,
    target_age VARCHAR(50) NOT NULL DEFAULT 'ADULTOS',
    date DATE NOT NULL,
    start_time TIME WITHOUT TIME ZONE NOT NULL,
    end_time TIME WITHOUT TIME ZONE NOT NULL,
    court_id UUID NOT NULL REFERENCES courts(id) ON DELETE CASCADE,
    coach_name VARCHAR(100) NOT NULL,
    max_students INTEGER NOT NULL DEFAULT 4,
    price_per_student INTEGER NOT NULL DEFAULT 35000,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

ALTER TABLE academy_classes ADD COLUMN IF NOT EXISTS target_age VARCHAR(50) NOT NULL DEFAULT 'ADULTOS';

CREATE INDEX IF NOT EXISTS idx_academy_classes_court_id ON academy_classes(court_id);
CREATE INDEX IF NOT EXISTS idx_academy_classes_date ON academy_classes(date);

-- ------------------------------------------------------------------------------
-- 9. TABLA: academy_enrollments
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academy_enrollments (
    id SERIAL PRIMARY KEY,
    academy_class_id INTEGER NOT NULL REFERENCES academy_classes(id) ON DELETE CASCADE,
    player_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    payment_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    amount_charged INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_academy_enrollments_class ON academy_enrollments(academy_class_id);
CREATE INDEX IF NOT EXISTS idx_academy_enrollments_player ON academy_enrollments(player_id);

-- ------------------------------------------------------------------------------
-- 10. TABLA: player_incidents
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS player_incidents (
    id SERIAL PRIMARY KEY,
    player_phone VARCHAR(50) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    slot_id INTEGER NOT NULL REFERENCES time_slots(id) ON DELETE CASCADE,
    incident_type VARCHAR(50) NOT NULL DEFAULT 'late_cancellation',
    description VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_player_incidents_phone ON player_incidents(player_phone);
CREATE INDEX IF NOT EXISTS idx_player_incidents_slot ON player_incidents(slot_id);

-- ------------------------------------------------------------------------------
-- 11. TABLA: products (Tienda y Bar)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL DEFAULT 'BEBIDAS',
    price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    stock INTEGER NOT NULL DEFAULT 0,
    is_membership_perk BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(name);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);

-- ------------------------------------------------------------------------------
-- 12. TABLA: orders
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    slot_id INTEGER REFERENCES time_slots(id) ON DELETE SET NULL,
    customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    customer_name VARCHAR(150) NOT NULL DEFAULT 'Cliente Barra',
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    payment_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_slot ON orders(slot_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);

-- ------------------------------------------------------------------------------
-- 13. TABLA: order_items
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    is_perk BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);

-- ------------------------------------------------------------------------------
-- 14. TABLA: club_presences (Recepción y Check-In)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS club_presences (
    id SERIAL PRIMARY KEY,
    player_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    player_name VARCHAR(150) NOT NULL,
    phone VARCHAR(50) NOT NULL DEFAULT '',
    check_in_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    check_out_time TIMESTAMP WITH TIME ZONE,
    is_inside BOOLEAN NOT NULL DEFAULT TRUE,
    membership_tier VARCHAR(50) NOT NULL DEFAULT 'ESTANDAR',
    current_slot_id INTEGER REFERENCES time_slots(id) ON DELETE SET NULL
);

ALTER TABLE club_presences ADD COLUMN IF NOT EXISTS membership_tier VARCHAR(50) NOT NULL DEFAULT 'ESTANDAR';
ALTER TABLE club_presences ADD COLUMN IF NOT EXISTS phone VARCHAR(50) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_club_presences_player ON club_presences(player_id);
CREATE INDEX IF NOT EXISTS idx_club_presences_is_inside ON club_presences(is_inside);

-- ------------------------------------------------------------------------------
-- 15. TABLA: competitor_clubs (Radar de Mercado)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competitor_clubs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    zone VARCHAR(100),
    address VARCHAR(250),
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    courts_count INTEGER DEFAULT 4,
    rating DOUBLE PRECISION DEFAULT 4.5,
    phone VARCHAR(50),
    website VARCHAR(250),
    price_valle NUMERIC(10, 2) DEFAULT 80000.00,
    price_pico NUMERIC(10, 2) DEFAULT 120000.00,
    is_target_partner BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_competitor_clubs_city ON competitor_clubs(city);
CREATE INDEX IF NOT EXISTS idx_competitor_clubs_partner ON competitor_clubs(is_target_partner);

-- ------------------------------------------------------------------------------
-- 16. TABLA: users (Staff y Autenticación)
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL DEFAULT 'STAFF_RECEPCION',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ------------------------------------------------------------------------------
-- 17. TABLA: audit_logs
-- ------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    username_snapshot VARCHAR(100) NOT NULL DEFAULT 'SISTEMA',
    action VARCHAR(60) NOT NULL,
    entity_name VARCHAR(60) NOT NULL,
    entity_id VARCHAR(100),
    details TEXT,
    ip_address VARCHAR(50),
    timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);


-- ==============================================================================
-- DATOS SEMILLA INICIALES: CAPITAL PÁDEL CLUB (MALOKA, BOGOTÁ)
-- ==============================================================================

-- 1. Club Principal
INSERT INTO clubs (id, name, slug, address, phone_contact, is_active, created_at)
VALUES (
    '2756f34a-7d24-4815-9f7e-6ed125ea5de7',
    'Capital Pádel Club – Maloka',
    'capital-padel-club-maloka',
    'Carrera 68D # 24A-51, Maloka, Bogotá, Colombia',
    '+573001234567',
    TRUE,
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    slug = EXCLUDED.slug,
    address = EXCLUDED.address,
    phone_contact = EXCLUDED.phone_contact,
    is_active = TRUE;

-- 2. Canchas Oficiales (5 Canchas de Pádel + Pistas Multideporte)
INSERT INTO courts (id, club_id, court_number, name, sport_type, max_capacity, is_active, created_at)
VALUES
    ('fd789df0-a503-4612-8fe2-f4e691df36a0', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 1, 'Cancha Central 1', 'PADEL', 4, TRUE, NOW()),
    ('7887da3c-30e2-4329-9abc-e7dd8d3a256b', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 2, 'Cancha 2', 'PADEL', 4, TRUE, NOW()),
    ('e46f79a1-12c9-4215-b14e-2e3b06596ff9', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 3, 'Cancha 3', 'PADEL', 4, TRUE, NOW()),
    ('d998c611-12d3-496b-83b0-12451d0eaa05', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 4, 'Cancha 4', 'PADEL', 4, TRUE, NOW()),
    ('1bf6e270-c684-4ecd-80f9-62b9439a41b9', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 5, 'Cancha 5', 'PADEL', 4, TRUE, NOW()),
    ('d8d342c4-a99d-4fc8-a038-3117357ccd7f', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 6, 'Pista Pickleball 1', 'PICKLEBALL', 4, TRUE, NOW()),
    ('3ef6543f-bffc-40dd-ae7a-a757819d88e4', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 7, 'Pista Pickleball 2', 'PICKLEBALL', 4, TRUE, NOW()),
    ('31dba8c2-30bd-4814-ba2f-016e984f6068', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 8, 'Cancha Arena Vóley', 'VOLLEYBALL', 12, TRUE, NOW()),
    ('966ed14e-d817-425a-977b-04d88a7f10b5', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 9, 'Estudio Pilates', 'PILATES', 10, TRUE, NOW()),
    ('7f0989d8-f6f5-483c-b2f3-e25a87d7e25a', '2756f34a-7d24-4815-9f7e-6ed125ea5de7', 10, 'Sala Gaming / Consola', 'CONSOLE', 4, TRUE, NOW())
ON CONFLICT (id) DO UPDATE SET
    club_id = EXCLUDED.club_id,
    court_number = EXCLUDED.court_number,
    name = EXCLUDED.name,
    sport_type = EXCLUDED.sport_type,
    max_capacity = EXCLUDED.max_capacity,
    is_active = TRUE;

-- 3. Planes de Membresía Oficiales
INSERT INTO membership_plans (id, name, start_time, end_time, max_daily_hours, includes_academy_classes, monthly_classes_count, includes_beverage_perk, americano_discount_pct, monthly_price_cop, badge_label, card_gradient, is_active, created_at)
VALUES
    (1, 'Tapia', '06:00:00', '23:59:00', 2.0, TRUE, 4, TRUE, 30, 350000, 'VIP PLATINUM', 'from-amber-600 via-yellow-600 to-amber-700', TRUE, NOW()),
    (2, 'Coello', '06:00:00', '23:59:00', 1.5, TRUE, 2, TRUE, 25, 280000, 'PRIME ACCESS', 'from-emerald-600 via-teal-600 to-cyan-700', TRUE, NOW()),
    (3, 'Galán', '06:00:00', '23:59:00', 1.5, FALSE, 0, TRUE, 20, 220000, 'PRO MATCH', 'from-blue-600 via-indigo-600 to-violet-700', TRUE, NOW()),
    (4, 'Chingotto', '06:00:00', '17:00:00', 1.5, FALSE, 0, FALSE, 15, 150000, 'HORARIO VALLE', 'from-slate-700 via-slate-800 to-indigo-900', TRUE, NOW()),
    (5, 'Lebrón', '12:00:00', '23:59:00', 1.5, FALSE, 0, FALSE, 20, 180000, 'AFTER WORK', 'from-purple-700 via-fuchsia-700 to-pink-700', TRUE, NOW())
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    start_time = EXCLUDED.start_time,
    end_time = EXCLUDED.end_time,
    max_daily_hours = EXCLUDED.max_daily_hours,
    includes_academy_classes = EXCLUDED.includes_academy_classes,
    monthly_classes_count = EXCLUDED.monthly_classes_count,
    includes_beverage_perk = EXCLUDED.includes_beverage_perk,
    americano_discount_pct = EXCLUDED.americano_discount_pct,
    monthly_price_cop = EXCLUDED.monthly_price_cop,
    badge_label = EXCLUDED.badge_label,
    card_gradient = EXCLUDED.card_gradient,
    is_active = TRUE;

-- Sincronizar secuencia de membership_plans
SELECT setval('membership_plans_id_seq', (SELECT COALESCE(MAX(id), 1) FROM membership_plans));

-- 4. Productos Iniciales para Bar y Recepción
INSERT INTO products (id, name, category, price, stock, is_membership_perk, created_at)
VALUES
    (1, 'Alquiler Pala', 'ALQUILER', 15000.00, 12, FALSE, NOW()),
    (2, 'Tubo de Bolas', 'EQUIPAMIENTO', 28000.00, 30, FALSE, NOW()),
    (3, 'Gatorade 500ml', 'BEBIDAS', 7000.00, 48, TRUE, NOW()),
    (4, 'Agua Cristal 600ml', 'BEBIDAS', 4000.00, 60, FALSE, NOW()),
    (5, 'Gaseosa Coca-Cola / Postobón', 'BEBIDAS', 5000.00, 36, FALSE, NOW()),
    (6, 'Paquete Papas / Snacks', 'SNACKS', 5000.00, 40, FALSE, NOW())
ON CONFLICT (id) DO NOTHING;

SELECT setval('products_id_seq', (SELECT COALESCE(MAX(id), 1) FROM products));

-- 5. Usuario Inicial Superadmin / Staff (Password: admin123)
INSERT INTO users (id, username, email, full_name, phone, hashed_password, role, is_active, created_at)
VALUES (
    1,
    'admin',
    'admin@capitalpadel.com',
    'Administrador Principal Capital Pádel',
    '+573001234567',
    '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW',
    'SUPERADMIN',
    TRUE,
    NOW()
)
ON CONFLICT (id) DO NOTHING;

SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 1) FROM users));
