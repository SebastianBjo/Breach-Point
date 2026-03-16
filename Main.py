import math
import random
import arcade
from typing import List, Tuple

# Constants
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 800
SCREEN_TITLE = "Tactical CQB - Vision Cone + Fog" 

PLAYER_SPEED = 240
PLAYER_RADIUS = 12
PLAYER_FOV_DEGREES = 90
PLAYER_VIEW_DISTANCE = 300

ENEMY_SPEED = 120
ENEMY_FOV_DEGREES = 90
ENEMY_VIEW_DISTANCE = 260

WALL_THICKNESS = 8

FOG_CELL = 20

# Colors
FLOOR_COLOR = arcade.color.DIM_GRAY
WALL_COLOR = arcade.color.LIGHT_GRAY
PLAYER_COLOR = arcade.color.SKY_BLUE
ENEMY_COLOR = arcade.color.CRIMSON
DOOR_COLOR = arcade.color.OLIVE


def clamp(x, minimum, maximum):
    return max(minimum, min(maximum, x))


def vector_from_angle(angle_radians: float) -> Tuple[float, float]:
    return math.cos(angle_radians), math.sin(angle_radians)


def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_on_segment(px, py, x1, y1, x2, y2):
    # check if point on segment
    cross = (py - y1) * (x2 - x1) - (px - x1) * (y2 - y1)
    if abs(cross) > 1e-5:
        return False
    dot = (px - x1) * (px - x2) + (py - y1) * (py - y2)
    return dot <= 0


def segment_intersection(p1, p2, p3, p4):
    # return intersection point of line seg p1p2 and p3p4 or None
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-6:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        ix = x1 + t * (x2 - x1)
        iy = y1 + t * (y2 - y1)
        return ix, iy
    return None


class Wall:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def draw(self):
        arcade.draw_line(self.x1, self.y1, self.x2, self.y2, WALL_COLOR, WALL_THICKNESS)

    def intersects_ray(self, sx, sy, ex, ey):
        inter = segment_intersection((sx, sy), (ex, ey), (self.x1, self.y1), (self.x2, self.y2))
        if not inter:
            return None
        d = dist((sx, sy), inter)
        return d, inter


class Door:
    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.is_open = True

    def draw(self):
        arcade.draw_line(self.x1, self.y1, self.x2, self.y2, DOOR_COLOR, WALL_THICKNESS)


class Player:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.angle = 0.0
        self.vx = 0
        self.vy = 0
        self.health = 100
        self.attack_cooldown = 0.0

    def update(self, delta_time, walls):
        speed = PLAYER_SPEED
        nx = self.x + self.vx * speed * delta_time
        ny = self.y + self.vy * speed * delta_time
        # collision with walls simple
        for wall in walls:
            # approximate wall as expanded line, avoid internal
            pass
        self.x = clamp(nx, 20, SCREEN_WIDTH - 20)
        self.y = clamp(ny, 20, SCREEN_HEIGHT - 20)
        self.attack_cooldown = max(0, self.attack_cooldown - delta_time)

    def draw(self):
        # draw player body
        arcade.draw_circle_filled(self.x, self.y, PLAYER_RADIUS, PLAYER_COLOR)
        # draw direction pointer
        dx, dy = vector_from_angle(self.angle)
        arcade.draw_line(self.x, self.y, self.x + dx * 22, self.y + dy * 22, arcade.color.WHITE, 3)
        arcade.draw_circle_outline(self.x, self.y, PLAYER_RADIUS + 1, arcade.color.BLACK)

    def shoot(self, target_x, target_y):
        if self.attack_cooldown > 0:
            return None
        self.attack_cooldown = 0.16
        dx = target_x - self.x
        dy = target_y - self.y
        mag = math.hypot(dx, dy)
        if mag < 1:
            return None
        return Bullet(self.x + dx / mag * 20, self.y + dy / mag * 20, dx / mag * 560, dy / mag * 560, arcade.color.YELLOW)


class Enemy:
    def __init__(self, x, y, patrol: List[Tuple[float, float]] = None):
        self.x = x
        self.y = y
        self.angle = 0
        self.health = 60
        self.patrol = patrol or []
        self.patrol_index = 0
        self.state = "guard"
        self.agro_time = 0
        self.shoot_cd = 0

    def draw(self):
        arcade.draw_circle_filled(self.x, self.y, 11, ENEMY_COLOR)
        dx, dy = vector_from_angle(self.angle)
        arcade.draw_line(self.x, self.y, self.x + dx * 16, self.y + dy * 16, arcade.color.BLACK, 2)

    def update(self, delta_time, player, walls):
        self.shoot_cd = max(0, self.shoot_cd - delta_time)
        if self.health <= 0:
            return

        seen, _ = self.can_see_player(player, walls)
        if seen:
            self.state = "aggressive"
            self.agro_time = 1.2

        if self.state == "aggressive":
            self.agro_time -= delta_time
            if self.agro_time <= 0:
                self.state = "guard"
        if self.state == "aggressive":
            # move toward player
            dx = player.x - self.x
            dy = player.y - self.y
            distp = math.hypot(dx, dy)
            if distp > 8:
                self.x += (dx / distp) * ENEMY_SPEED * delta_time
                self.y += (dy / distp) * ENEMY_SPEED * delta_time
            self.angle = math.atan2(dy, dx)
        elif self.patrol:
            tx, ty = self.patrol[self.patrol_index]
            dx = tx - self.x
            dy = ty - self.y
            d = math.hypot(dx, dy)
            if d < 8:
                self.patrol_index = (self.patrol_index + 1) % len(self.patrol)
            else:
                self.angle = math.atan2(dy, dx)
                self.x += (dx / d) * ENEMY_SPEED * delta_time
                self.y += (dy / d) * ENEMY_SPEED * delta_time

    def can_see_player(self, player, walls):
        dx = player.x - self.x
        dy = player.y - self.y
        d = math.hypot(dx, dy)
        if d > ENEMY_VIEW_DISTANCE:
            return False, None
        dirx, diry = vector_from_angle(self.angle)
        dot = (dx * dirx + dy * diry) / (d + 1e-9)
        if dot < math.cos(math.radians(ENEMY_FOV_DEGREES / 2)):
            return False, None
        # raycast to player
        blocked = False
        for wall in walls:
            if segment_intersection((self.x, self.y), (player.x, player.y), (wall.x1, wall.y1), (wall.x2, wall.y2)):
                blocked = True
                break
        return not blocked, d


class Bullet:
    def __init__(self, x, y, vx, vy, color):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = 1.2

    def update(self, delta_time):
        self.life -= delta_time
        self.x += self.vx * delta_time
        self.y += self.vy * delta_time

    def draw(self):
        arcade.draw_circle_filled(self.x, self.y, 3, self.color)


class Map:
    def __init__(self):
        self.walls: List[Wall] = []
        self.doors: List[Door] = []
        self.create_room_layout()

    def create_room_layout(self):
        # Outer boundary
        self._rect_walls(50, 50, SCREEN_WIDTH - 50, SCREEN_HEIGHT - 50)

        # interior rooms
        self._rect_walls(120, 120, 520, 380)
        self._rect_walls(680, 100, 1200, 360)
        self._rect_walls(130, 450, 520, 720)
        self._rect_walls(680, 430, 1200, 720)

        # hallways between rooms
        self.doors.append(Door(520, 250, 680, 250))
        self.doors.append(Door(520, 560, 680, 560))
        self.doors.append(Door(320, 380, 320, 450))
        self.doors.append(Door(880, 380, 880, 450))

    def _rect_walls(self, x1, y1, x2, y2):
        self.walls.append(Wall(x1, y1, x2, y1))
        self.walls.append(Wall(x2, y1, x2, y2))
        self.walls.append(Wall(x2, y2, x1, y2))
        self.walls.append(Wall(x1, y2, x1, y1))

    def draw(self):
        # floor
        arcade.draw_lrtb_rectangle_filled(50, SCREEN_WIDTH - 50, SCREEN_HEIGHT - 50, 50, arcade.color.DARK_SLATE_GRAY)
        for wall in self.walls:
            wall.draw()
        for door in self.doors:
            door.draw()


class TacticalGame(arcade.Window):
    def __init__(self):
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE)
        arcade.set_background_color(arcade.color.BLACK)
        self.map = Map()
        self.player = Player(200, 200)
        self.enemies: List[Enemy] = []
        self.bullets: List[Bullet] = []
        self.keys = set()
        self.vision_polygon = []
        self.fog_width = SCREEN_WIDTH // FOG_CELL + 2
        self.fog_height = SCREEN_HEIGHT // FOG_CELL + 2
        self.fog_seen = [[False for _ in range(self.fog_height)] for _ in range(self.fog_width)]
        self.fog_current = [[False for _ in range(self.fog_height)] for _ in range(self.fog_width)]
        self.game_over = False
        self.victory = False
        self.init_enemies()

    def init_enemies(self):
        self.enemies.append(Enemy(350, 300, patrol=[(350, 300), (470, 300)]))
        self.enemies.append(Enemy(800, 280, patrol=[(800, 280), (980, 280)]))
        self.enemies.append(Enemy(250, 620, patrol=[(250, 620), (440, 620)]))
        self.enemies.append(Enemy(960, 620, patrol=[(960, 620), (760, 620)]))

    def on_draw(self):
        arcade.start_render()
        self.map.draw()
        for enemy in self.enemies:
            if enemy.health <= 0:
                continue
            arcade.draw_circle_filled(enemy.x, enemy.y, 12, arcade.color.DARK_RED)
            enemy.draw()
        self.player.draw()
        for bullet in self.bullets:
            bullet.draw()

        self.draw_vision_and_fog()
        self.draw_ui()

    def draw_ui(self):
        arcade.draw_text(f"Health: {self.player.health}", 20, SCREEN_HEIGHT - 30, arcade.color.WHITE, 14)
        arcade.draw_text(f"Enemies left: {len([e for e in self.enemies if e.health > 0])}", 160, SCREEN_HEIGHT - 30, arcade.color.WHITE, 14)
        if self.game_over:
            msg = "VICTORY" if self.victory else "DEFEAT"
            color = arcade.color.LIME if self.victory else arcade.color.RED
            arcade.draw_text(msg, SCREEN_WIDTH/2 - 120, SCREEN_HEIGHT/2, color, 48, anchor_x="center")
            arcade.draw_text("Press R to restart", SCREEN_WIDTH/2 - 110, SCREEN_HEIGHT/2 - 60, arcade.color.WHITE, 20, anchor_x="center")

    def draw_vision_and_fog(self):
        # compute visible polygon each frame
        self.vision_polygon = self.compute_vision_cone(self.player.x, self.player.y, self.player.angle, PLAYER_FOV_DEGREES, PLAYER_VIEW_DISTANCE)
        self.update_fog()

        # draw dark overlay by per-cell
        for i in range(self.fog_width):
            for j in range(self.fog_height):
                x = i * FOG_CELL
                y = j * FOG_CELL
                visible_now = self.fog_current[i][j]
                seen = self.fog_seen[i][j]
                if visible_now:
                    continue
                alpha = 200 if not seen else 120
                arcade.draw_lrtb_rectangle_filled(x, x + FOG_CELL, y + FOG_CELL, y, (0, 0, 0, alpha))

        # Draw vision cone edge
        if len(self.vision_polygon) > 2:
            arcade.draw_polygon_outline(self.vision_polygon, arcade.color.LIGHT_YELLOW, 1)

    def update_fog(self):
        # reset current
        for i in range(self.fog_width):
            for j in range(self.fog_height):
                self.fog_current[i][j] = False
        # fill cells that are in polygon
        for i in range(self.fog_width):
            for j in range(self.fog_height):
                cx = i * FOG_CELL + FOG_CELL / 2
                cy = j * FOG_CELL + FOG_CELL / 2
                if self.point_in_polygon((cx, cy), self.vision_polygon):
                    self.fog_current[i][j] = True
                    self.fog_seen[i][j] = True

    def point_in_polygon(self, point, poly):
        # ray casting
        x, y = point
        inside = False
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-9) + x1):
                inside = not inside
        return inside

    def compute_vision_cone(self, px, py, angle, fov, distance):
        segments = [wall for wall in self.map.walls]
        vision_points = []
        half = fov / 2
        step = 2
        for a in range(-int(half), int(half)+1, step):
            ray_angle = angle + math.radians(a)
            dx = math.cos(ray_angle)
            dy = math.sin(ray_angle)
            far_x = px + dx * distance
            far_y = py + dy * distance
            closest = (far_x, far_y)
            closest_d = distance
            for wall in segments:
                inter = segment_intersection((px, py), (far_x, far_y), (wall.x1, wall.y1), (wall.x2, wall.y2))
                if inter:
                    d = dist((px, py), inter)
                    if d < closest_d:
                        closest_d = d
                        closest = inter
            vision_points.append(closest)
        return [(px, py)] + vision_points

    def on_update(self, delta_time):
        if self.game_over:
            return
        # update player movement
        vx = vy = 0
        if arcade.key.W in self.keys:
            vy += 1
        if arcade.key.S in self.keys:
            vy -= 1
        if arcade.key.A in self.keys:
            vx -= 1
        if arcade.key.D in self.keys:
            vx += 1
        mag = math.hypot(vx, vy)
        if mag > 0:
            vx /= mag
            vy /= mag
        self.player.vx = vx
        self.player.vy = vy
        self.player.update(delta_time, self.map.walls)

        # Enemy updates
        for enemy in self.enemies:
            enemy.update(delta_time, self.player, self.map.walls)
            # enemy shooting player
            seen, distp = enemy.can_see_player(self.player, self.map.walls)
            if seen and distp < ENEMY_VIEW_DISTANCE and enemy.shoot_cd <= 0:
                enemy.shoot_cd = 0.7
                # direct instant hit if player in range
                if distp < 220:
                    self.player.health -= 12
                    if self.player.health <= 0:
                        self.player.health = 0
                        self.game_over = True
                        self.victory = False

        # bullets
        new_bullets = []
        for bullet in self.bullets:
            bullet.update(delta_time)
            if bullet.life <= 0:
                continue
            hit = False
            for enemy in self.enemies:
                if enemy.health <= 0:
                    continue
                if dist((bullet.x, bullet.y), (enemy.x, enemy.y)) < 16:
                    enemy.health -= 40
                    hit = True
                    break
            if hit:
                continue
            if bullet.x < 0 or bullet.x > SCREEN_WIDTH or bullet.y < 0 or bullet.y > SCREEN_HEIGHT:
                continue
            # barrier collisions
            blocked = False
            for w in self.map.walls:
                if abs((w.y2 - w.y1) * bullet.x - (w.x2 - w.x1) * bullet.y + w.x2 * w.y1 - w.y2 * w.x1) < 20:
                    blocked = True
                    break
            if blocked:
                continue
            new_bullets.append(bullet)
        self.bullets = new_bullets

        if all(enemy.health <= 0 for enemy in self.enemies):
            self.game_over = True
            self.victory = True

    def on_key_press(self, key, modifiers):
        if key == arcade.key.R and self.game_over:
            self.__init__()
            return
        if key == arcade.key.E:
            # interact with doors could open/close eventually
            pass
        self.keys.add(key)

    def on_key_release(self, key, modifiers):
        if key in self.keys:
            self.keys.remove(key)

    def on_mouse_motion(self, x, y, dx, dy):
        self.player.angle = math.atan2(y - self.player.y, x - self.player.x)

    def on_mouse_press(self, x, y, button, modifiers):
        if button == arcade.MOUSE_BUTTON_LEFT and not self.game_over:
            bullet = self.player.shoot(x, y)
            if bullet:
                self.bullets.append(bullet)


def main():
    game = TacticalGame()
    arcade.run()


if __name__ == "__main__":
    main()
