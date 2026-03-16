import math
import random
import sys
import pygame

# --- Constants ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

GRID_SIZE = 16

PLAYER_SPEED = 200
PLAYER_RADIUS = 14
PLAYER_FOV = math.radians(50)
PLAYER_VIEW_DISTANCE = 1000

ENEMY_SPEED = 100
ENEMY_RADIUS = 13
ENEMY_FOV = math.radians(50)
ENEMY_VIEW_DISTANCE = 1000

BULLET_SPEED = 1000
BULLET_LIFETIME = 2.0


# --- Geometry helpers ---

def clamp(v, a, b):
    return max(a, min(b, v))


def segment_intersect(p1, p2, q1, q2):
    # returns (ix, iy, t, u) if intersects else None
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = q1
    x4, y4 = q2
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return ix, iy, t, u
    return None


def point_in_polygon(x, y, polygon):
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1):
            inside = not inside
    return inside


def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def line_intersects_walls(p1, p2, walls):
    for wall in walls:
        # wall is (x,y,w,h)
        x, y, w, h = wall
        edges = [((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)), ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))]
        for e in edges:
            if segment_intersect(p1, p2, e[0], e[1]):
                return True
    return False


# --- Map ---
class Map:
    def __init__(self):
        self.walls = []
        self.doors = []
        self.build_map()

    def build_map(self):
        # Outer walls
        self.walls.append((0, 0, SCREEN_WIDTH, 20))
        self.walls.append((0, 0, 20, SCREEN_HEIGHT))
        self.walls.append((SCREEN_WIDTH-20, 0, 20, SCREEN_HEIGHT))
        self.walls.append((0, SCREEN_HEIGHT-20, SCREEN_WIDTH, 20))

        # Rooms and corridors
        self.walls.extend([
            (120, 60, 20, 520),
            (120, 60, 640, 20),
            (740, 60, 20, 320),
            (320, 320, 440, 20),
            (320, 320, 20, 250),
            (220, 420, 120, 20),
            (220, 420, 20, 180),
            (220, 580, 360, 20),
            (560, 380, 20, 220),
            (760, 380, 360, 20),
            (1100, 380, 20, 180),
            (880, 120, 20, 220),
            (760, 120, 340, 20),
            (760, 120, 20, 180),
        ])

        # doors: (x,y,w,h,open)
        self.doors.append([740, 160, 20, 60, False])
        self.doors.append([380, 300, 60, 20, False])

    def collides(self, rect):
        r = pygame.Rect(rect)
        for wall in self.walls:
            if r.colliderect(pygame.Rect(wall)):
                return True
        for door in self.doors:
            if not door[4] and r.colliderect(pygame.Rect(door[0], door[1], door[2], door[3])):
                return True
        return False

    def draw(self, surf, is_faint=False):
        # floor
        floor = (128, 128, 128) if is_faint else (211, 211, 211)
        surf.fill((220, 220, 220))
        for y in range(0, SCREEN_HEIGHT, 64):
            for x in range(0, SCREEN_WIDTH, 64):
                pygame.draw.rect(surf, floor, (x, y, 64, 64), 0)
                pygame.draw.rect(surf, (floor[0]+10, floor[1]+10, floor[2]+10), (x, y, 64, 64), 1)

        wall_color = (66, 68, 74) if is_faint else (180, 180, 180)
        for wall in self.walls:
            pygame.draw.rect(surf, wall_color, wall)
        for door in self.doors:
            color = (80, 30, 0) if not door[4] else (100, 120, 50)
            pygame.draw.rect(surf, color, (door[0], door[1], door[2], door[3]))

    def toggle_door_at(self, px, py):
        for door in self.doors:
            dx, dy, dw, dh, open_flag = door
            if dx <= px <= dx + dw and dy <= py <= dy + dh:
                door[4] = not door[4]
                return True
        return False

    def get_block_segments(self):
        segments = []
        for wall in self.walls:
            x, y, w, h = wall
            segments.append(((x, y), (x + w, y)))
            segments.append(((x + w, y), (x + w, y + h)))
            segments.append(((x + w, y + h), (x, y + h)))
            segments.append(((x, y + h), (x, y)))
        for door in self.doors:
            if not door[4]:
                x, y, w, h, _ = door
                segments.append(((x, y), (x + w, y)))
                segments.append(((x + w, y), (x + w, y + h)))
                segments.append(((x + w, y + h), (x, y + h)))
                segments.append(((x, y + h), (x, y)))
        return segments


# --- Player ---
class Player:
    def __init__(self, x, y):
        self.pos = pygame.math.Vector2(x, y)
        self.angle = 0
        self.health = 100
        self.radius = PLAYER_RADIUS
        self.reload = 0

    def update(self, dt, keys, game_map):
        move = pygame.math.Vector2(0, 0)
        if keys[pygame.K_w]: move.y -= 1
        if keys[pygame.K_s]: move.y += 1
        if keys[pygame.K_a]: move.x -= 1
        if keys[pygame.K_d]: move.x += 1
        if move.length_squared() > 0:
            move = move.normalize() * PLAYER_SPEED * dt
            newpos = self.pos + move
            rect = (newpos.x - self.radius, newpos.y - self.radius, self.radius * 2, self.radius * 2)
            if not game_map.collides(rect):
                self.pos = newpos

    def set_aim(self, mx, my):
        self.angle = math.atan2(my - self.pos.y, mx - self.pos.x)

    def draw(self, surf, is_faint=False):
        color = (50, 220, 255) if not is_faint else (60, 130, 180)
        pygame.draw.circle(surf, color, (int(self.pos.x), int(self.pos.y)), self.radius)
        dx = math.cos(self.angle) * self.radius
        dy = math.sin(self.angle) * self.radius
        pygame.draw.line(surf, (255, 255, 255), (self.pos.x, self.pos.y), (self.pos.x + dx, self.pos.y + dy), 3)


# --- Enemy ---
class Enemy:
    def __init__(self, x, y, patrol=None):
        self.pos = pygame.math.Vector2(x, y)
        self.angle = 0
        self.health = 100
        self.radius = ENEMY_RADIUS
        self.patrol = patrol or []
        self.patrol_idx = 0
        self.state = 'guard'
        self.seen_player = False
        self.shoot_timer = 0

    def update(self, dt, player, game_map):
        if self.health <= 0:
            return
        self.angle = math.atan2(player.pos.y - self.pos.y, player.pos.x - self.pos.x)
        if self.can_see_player(player, game_map):
            self.state = 'engage'
            self.seen_player = True
        elif self.state == 'engage':
            self.state = 'guard'

        if self.state == 'engage':
            dir = (player.pos - self.pos)
            if dir.length_squared() > 4:
                dir = dir.normalize() * ENEMY_SPEED * dt
                newpos = self.pos + dir
                rect = (newpos.x - self.radius, newpos.y - self.radius, self.radius * 2, self.radius * 2)
                if not game_map.collides(rect):
                    self.pos = newpos
            self.shoot_timer += dt
        else:
            self.patrol_timer(dt, game_map)

    def patrol_timer(self, dt, game_map):
        if not self.patrol:
            return
        target = pygame.math.Vector2(self.patrol[self.patrol_idx])
        dir = target - self.pos
        if dir.length_squared() < 25:
            self.patrol_idx = (self.patrol_idx + 1) % len(self.patrol)
            return
        dir = dir.normalize() * ENEMY_SPEED * dt
        newpos = self.pos + dir
        rect = (newpos.x - self.radius, newpos.y - self.radius, self.radius * 2, self.radius * 2)
        if not game_map.collides(rect):
            self.pos = newpos

    def can_see_player(self, player, game_map):
        if self.health <= 0:
            return False
        d = player.pos - self.pos
        dist2 = d.length_squared()
        if dist2 > ENEMY_VIEW_DISTANCE**2:
            return False
        angle_to_player = math.atan2(d.y, d.x)
        delta = (angle_to_player - self.angle + math.pi) % (2*math.pi) - math.pi
        if abs(delta) > ENEMY_FOV / 2:
            return False
        if line_intersects_walls(self.pos, player.pos, game_map.walls):
            return False
        for door in game_map.doors:
            if not door[4] and line_intersects_walls(self.pos, player.pos, [door[:4]]):
                return False
        return True

    def draw(self, surf, is_faint=False):
        if self.health <= 0:
            return
        color = (220, 60, 60) if not is_faint else (130, 70, 70)
        pygame.draw.circle(surf, color, (int(self.pos.x), int(self.pos.y)), self.radius)
        dx = math.cos(self.angle) * self.radius
        dy = math.sin(self.angle) * self.radius
        pygame.draw.line(surf, (255, 255, 0), (self.pos.x, self.pos.y), (self.pos.x + dx, self.pos.y + dy), 2)


# --- Bullet ---
class Bullet:
    def __init__(self, x, y, angle, owner):
        self.pos = pygame.math.Vector2(x, y)
        self.vel = pygame.math.Vector2(math.cos(angle), math.sin(angle)) * BULLET_SPEED
        self.life = BULLET_LIFETIME
        self.owner = owner

    def update(self, dt):
        self.pos += self.vel * dt
        self.life -= dt

    def draw(self, surf):
        pygame.draw.circle(surf, (255, 230, 100), (int(self.pos.x), int(self.pos.y)), 4)


# --- Vision System ---
class Vision:
    def __init__(self, game_map):
        self.game_map = game_map
        self.approx = []
        self.seen_tiles = set()

    def compute_fov_polygon(self, player):
        start = (player.pos.x, player.pos.y)
        segments = self.game_map.get_block_segments()
        points = []
        ray_count = 80
        for i in range(ray_count + 1):
            angle = player.angle - PLAYER_FOV/2 + (PLAYER_FOV * i / ray_count)
            dx = math.cos(angle)
            dy = math.sin(angle)
            best = None
            best_dist = PLAYER_VIEW_DISTANCE
            end = (start[0] + dx * PLAYER_VIEW_DISTANCE, start[1] + dy * PLAYER_VIEW_DISTANCE)
            for seg in segments:
                r = segment_intersect(start, end, seg[0], seg[1])
                if r:
                    ix, iy, t, u = r
                    d = math.hypot(ix - start[0], iy - start[1])
                    if d < best_dist:
                        best = (ix, iy)
                        best_dist = d
            if best is None:
                points.append(end)
            else:
                points.append(best)
        poly = [start] + points
        return poly


# --- Game ---
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Breach Point: CQB Demo")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 30)
        self.memory_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.memory_surf.fill((0, 0, 0))

        self.game_map = Map()
        self.player = Player(170, 120)
        self.enemies = [
            Enemy(500, 220, [(500, 220), (620, 220), (620, 300), (500, 300)]),
            Enemy(980, 500, [(980, 500), (1080, 500), (1080, 600), (980, 600)]),
            Enemy(620, 120, []),
        ]
        self.bullets = []
        self.vision = Vision(self.game_map)

        self.explored = [[False] * (SCREEN_WIDTH // GRID_SIZE + 1) for _ in range(SCREEN_HEIGHT // GRID_SIZE + 1)]

        self.victory = False
        self.defeat = False

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            if not self.victory and not self.defeat:
                self.update(dt)
            self.draw()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()
                if event.key == pygame.K_e:
                    self.game_map.toggle_door_at(self.player.pos.x, self.player.pos.y)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if not self.victory and not self.defeat:
                    self.fire_bullet()

    def fire_bullet(self):
        b = Bullet(self.player.pos.x + math.cos(self.player.angle) * 20,
                   self.player.pos.y + math.sin(self.player.angle) * 20,
                   self.player.angle,
                   'player')
        self.bullets.append(b)

    def update(self, dt):
        mx, my = pygame.mouse.get_pos()
        keys = pygame.key.get_pressed()
        self.player.set_aim(mx, my)
        self.player.update(dt, keys, self.game_map)

        for enemy in self.enemies:
            enemy.update(dt, self.player, self.game_map)

        for b in self.bullets:
            b.update(dt)

        self.handle_bullets()
        self.update_visibility()
        self.check_game_state()

    def handle_bullets(self):
        next_bullets = []
        for b in self.bullets:
            if b.life <= 0:
                continue
            if b.pos.x < 0 or b.pos.x > SCREEN_WIDTH or b.pos.y < 0 or b.pos.y > SCREEN_HEIGHT:
                continue
            # wall collision
            if self.game_map.collides((b.pos.x - 2, b.pos.y - 2, 4, 4)):
                continue

            if b.owner == 'player':
                for enemy in self.enemies:
                    if enemy.health > 0 and dist((b.pos.x, b.pos.y), enemy.pos) < enemy.radius + 3:
                        enemy.health -= 50
                        break
                else:
                    next_bullets.append(b)
            else:
                if dist((b.pos.x, b.pos.y), self.player.pos) < self.player.radius + 4:
                    self.player.health -= 25
                else:
                    next_bullets.append(b)
        self.bullets = next_bullets

        # enemy shooting into player when in view
        for enemy in self.enemies:
            if enemy.health > 0 and enemy.state == 'engage':
                if enemy.shoot_timer >= 0.7:
                    d = self.player.pos - enemy.pos
                    if d.length_squared() < ENEMY_VIEW_DISTANCE**2:
                        enemy.shoot_timer = 0
                        angle = math.atan2(d.y, d.x)
                        self.bullets.append(Bullet(enemy.pos.x + math.cos(angle) * 18,
                                                   enemy.pos.y + math.sin(angle) * 18,
                                                   angle, 'enemy'))

    def update_visibility(self):
        poly = self.vision.compute_fov_polygon(self.player)
        minx = max(0, int(self.player.pos.x - PLAYER_VIEW_DISTANCE))
        maxx = min(SCREEN_WIDTH - 1, int(self.player.pos.x + PLAYER_VIEW_DISTANCE))
        miny = max(0, int(self.player.pos.y - PLAYER_VIEW_DISTANCE))
        maxy = min(SCREEN_HEIGHT - 1, int(self.player.pos.y + PLAYER_VIEW_DISTANCE))
        for gy in range(miny // GRID_SIZE, maxy // GRID_SIZE + 1):
            for gx in range(minx // GRID_SIZE, maxx // GRID_SIZE + 1):
                cx = gx * GRID_SIZE + GRID_SIZE / 2
                cy = gy * GRID_SIZE + GRID_SIZE / 2
                if point_in_polygon(cx, cy, poly):
                    if 0 <= gy < len(self.explored) and 0 <= gx < len(self.explored[0]):
                        self.explored[gy][gx] = True

    def check_game_state(self):
        if self.player.health <= 0:
            self.defeat = True
        if all(enemy.health <= 0 for enemy in self.enemies):
            self.victory = True

    def draw(self):
    # 1. Clean black slate
    self.screen.fill((0,0,0))

    # 2. Get the player's current field of view
    poly = self.vision.compute_fov_polygon(self.player)

    # 3. Create the Fog (Background Darkness)
    fog = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    fog.fill((0, 0, 0, 255))  # Pure black
    if len(poly) > 2:
        pygame.draw.polygon(fog, (0, 0, 0, 0), poly) # Cut out current vision
    self.screen.blit(fog, (0, 0))

    # 4. Draw "Memories" on top of the dark fog
    for gy in range(len(self.explored)):
        for gx in range(len(self.explored[0])):
            if self.explored[gy][gx]:
                cell_rect = pygame.Rect(gx * GRID_SIZE, gy * GRID_SIZE, GRID_SIZE, GRID_SIZE)
                pygame.draw.rect(self.screen, (40, 40, 40), cell_rect)

    # Draw faint walls/doors for explored areas
    for wall in self.game_map.walls:
        if self.rect_discovered(wall):
            pygame.draw.rect(self.screen, (60, 60, 60), wall)
            
    for door in self.game_map.doors:
        if self.rect_discovered(door[:4]):
            # Darkened door colors (brown or green)
            c = (70, 40, 20) if not door[4] else (50, 70, 45)
            pygame.draw.rect(self.screen, c, (door[0], door[1], door[2], door[3]))

    # 5. Draw the "Bright Now" (Current FOV)
    # This draws over the memory with full colors/moving enemies
    self.draw_visible_objects(poly)

    # 6. UI
    self.draw_ui()
    pygame.display.flip()

if __name__ == "__main__":
    game = Game()
    game.run()
