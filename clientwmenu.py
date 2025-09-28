import os
import sys
import json
import socket
import pygame
from pygame import display, draw, font, event, key, mixer, time
from pygame.locals import QUIT, K_w, K_s, K_r, K_UP, K_DOWN, K_RETURN, K_ESCAPE, MOUSEBUTTONDOWN
from threading import Thread
from collections import deque

# --- PYGAME НАЛАШТУВАННЯ ---
WIDTH, HEIGHT = 800, 600
FPS = 60
PADDLE_WIDTH = 20
PADDLE_HEIGHT = 100
PADDLE_RADIUS = 10  # Радіус заокруглення
BALL_RADIUS = 10

TRAIL_LENGTH = 20      # Довжина трейлу
TRAIL_FADE_SPEED = 15  # Швидкість зникнення трейлу

# --- КОЛЬОРИ ---
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
MAGENTA = (255, 0, 255)
GOLD = (255, 215, 0)
DARK_GRAY = (30, 30, 30)
DARKER_GRAY = (20, 20, 20)
PURPLE = (128, 0, 255)
ACCENT = (90, 200, 255)

# --- СТАНИ ---
STATE_MENU = "menu"
STATE_GAME = "game"

# --- ІНІЦІАЛІЗАЦІЯ Pygame ---
pygame.init()
screen = display.set_mode((WIDTH, HEIGHT))
clock = time.Clock()
display.set_caption("Пінг-Понг")

# --- ШРИФТИ ---
font_title = font.Font(None, 96)
font_win = font.Font(None, 72)
font_main = font.Font(None, 36)
font_countdown = font.Font(None, 72)
font_small = font.Font(None, 28)

# --- ЗВУКИ ---
sounds_enabled = False
BACKGROUND_MUSIC_FILE = "background_music.mp3"  # <--- Шлях до фонової музики
try:
    mixer.init()
    sound_platform = mixer.Sound("pingball.wav")
    sound_wall = mixer.Sound("ball-bounce.wav")
    sound_platform.set_volume(0.4)
    sound_wall.set_volume(0.5)

    # Завантаження фонової музики
    if os.path.exists(BACKGROUND_MUSIC_FILE):
        mixer.music.load(BACKGROUND_MUSIC_FILE)
        mixer.music.set_volume(0.3)  # Трохи тихіше за ефекти
        mixer.music.play(-1)         # Повторювати нескінченно
        print("Фонова музика запущена.")
    else:
        print(f"Попередження: Файл фонової музики '{BACKGROUND_MUSIC_FILE}' не знайдено.")

    sounds_enabled = True
except Exception:
    sounds_enabled = False

# --- СПРАЙТИ/ЗОБРАЖЕННЯ ---
ASSETS_DIR = "assets"

def load_image(file_name, size=None):
    path = os.path.join(ASSETS_DIR, file_name)
    try:
        img = pygame.image.load(path).convert_alpha()
        if size:
            img = pygame.transform.smoothscale(img, size)
        return img
    except Exception as e:
        print(f"Попередження: не вдалося завантажити {file_name}: {e}")
        return None

BACKGROUND_IMG    = load_image("background.jpg", (WIDTH, HEIGHT))
PADDLE_IMG_LEFT   = load_image("paddle_left.png",  (50,50))
PADDLE_IMG_RIGHT  = load_image("paddle_right.png", (50,50))
BALL_IMG          = load_image("ball.png", (BALL_RADIUS * 3, BALL_RADIUS * 3))
SCORE_BG_LEFT_IMG = load_image("score_left.png")   # масштабуємо при рендері
SCORE_BG_RIGHT_IMG= load_image("score_right.png")  # масштабуємо при рендері

# Розмір спрайтів під фон рахунку
SCORE_BG_SIZE = (50,50)

# --- КЛАС ДЛЯ ТРЕЙЛУ М'ЯЧА ---
class BallTrail:
    def __init__(self, max_length=TRAIL_LENGTH):
        self.positions = deque(maxlen=max_length)  # елементи виду (x, y, alpha)
        self.max_length = max_length

    def add_position(self, x, y):
        self.positions.append((x, y, 255))

    def update(self):
        new_positions = deque(maxlen=self.max_length)
        for x, y, alpha in self.positions:
            new_alpha = max(0, alpha - TRAIL_FADE_SPEED)
            if new_alpha > 0:
                new_positions.append((x, y, new_alpha))
        self.positions = new_positions

    def draw(self, screen):
        length = len(self.positions)
        if length <= 1:
            return
        for i, (x, y, alpha) in enumerate(self.positions):
            if i < length - 1:  # не малюємо останню позицію (поточний м'яч)
                t = max(0.05, i / length)
                size = int(BALL_RADIUS * t)
                if size > 0:
                    trail_surface = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                    color = (*PURPLE, int(alpha * t))
                    pygame.draw.circle(trail_surface, color, (size, size), size)
                    screen.blit(trail_surface, (int(x - size), int(y - size)))

# --- МЕРЕЖЕВІ ФУНКЦІЇ ---
def connect_to_server(host='localhost', port=8080):
    """Підключення до ігрового сервера"""
    while True:
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect((host, port))
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.settimeout(0.1)

            data = client.recv(24).decode()
            my_id = int(data.strip())
            print(f"Підключено до сервера. ID гравця: {my_id}")
            return client, my_id
        except ConnectionRefusedError:
            print("Сервер недоступний. Спроба підключення...")
            pygame.time.wait(1000)
        except Exception as e:
            print(f"Помилка підключення: {e}")
            pygame.time.wait(1000)

def receive_data(client, game_state, buffer):
    """Отримання даних від сервера в окремому потоці"""
    while game_state.get('running', True):
        try:
            data = client.recv(1024).decode()
            if not data:
                break

            buffer['data'] += data

            # Обробка повних пакетів, розділених символом нового рядка
            while "\n" in buffer['data']:
                packet, buffer['data'] = buffer['data'].split("\n", 1)
                if packet.strip():
                    try:
                        new_state = json.loads(packet)
                        game_state.update(new_state)
                    except json.JSONDecodeError:
                        print(f"Помилка декодування JSON: {packet}")
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Помилка отримання даних: {e}")
            game_state['winner'] = -1
            game_state['disconnected'] = True
            break

# Якщо сервер очікує команди без переносу рядка — лишаємо як є.
# Якщо потрібен перенос, встанови COMMAND_APPEND_NEWLINE = True.
COMMAND_APPEND_NEWLINE = False

def send_command(client, command):
    """Безпечне відправлення команди на сервер"""
    try:
        if COMMAND_APPEND_NEWLINE:
            client.send((command + "\n").encode())
        else:
            client.send(command.encode())
    except Exception:
        pass

# --- ФУНКЦІЇ МАЛЮВАННЯ ---
def draw_rounded_paddle(screen, x, y, width, height, color, radius):
    """Малює платформу з заокругленими кутами (fallback, якщо немає спрайта)"""
    draw.rect(screen, color, (x + radius, y, width - 2 * radius, height))
    draw.rect(screen, color, (x, y + radius, width, height - 2 * radius))
    draw.circle(screen, color, (x + radius, y + radius), radius)
    draw.circle(screen, color, (x + width - radius, y + radius), radius)
    draw.circle(screen, color, (x + radius, y + height - radius), radius)
    draw.circle(screen, color, (x + width - radius, y + height - radius), radius)

def draw_score_box_sprite(screen, center_pos, text, font_obj, bg_img, text_color=WHITE):
    """Малює бокс рахунку з фоновим спрайтом (або fallback на прямокутник)"""
    if bg_img:
        img = pygame.transform.smoothscale(bg_img, SCORE_BG_SIZE)
        rect = img.get_rect(center=center_pos)
        screen.blit(img, rect.topleft)
        text_surf = font_obj.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=rect.center)
        screen.blit(text_surf, text_rect)
    else:
        # Fallback: напівпрозорий прямокутник
        SCORE_BG_COLOR = (0, 0, 0, 170)
        SCORE_PADDING_X = 16
        SCORE_PADDING_Y = 10
        SCORE_BORDER_RADIUS = 12
        text_surf = font_obj.render(text, True, text_color)
        tw, th = text_surf.get_size()
        box_surf = pygame.Surface((tw + SCORE_PADDING_X * 2, th + SCORE_PADDING_Y * 2), pygame.SRCALPHA)
        pygame.draw.rect(box_surf, SCORE_BG_COLOR, box_surf.get_rect(), border_radius=SCORE_BORDER_RADIUS)
        text_rect = text_surf.get_rect(center=(box_surf.get_width() // 2, box_surf.get_height() // 2))
        box_surf.blit(text_surf, text_rect)
        screen.blit(box_surf, box_surf.get_rect(center=center_pos))

def draw_game(screen, game_state, my_id, ball_trail):
    """Малювання ігрового поля"""
    # Фон
    if BACKGROUND_IMG:
        screen.blit(BACKGROUND_IMG, (0, 0))
    else:
        screen.fill(DARK_GRAY)

    # Центральна пунктирна лінія
    for y in range(0, HEIGHT, 20):
        draw.rect(screen, WHITE, (WIDTH // 2 - 2, y, 4, 10))

    # Платформи зі спрайтами (або fallback)
    if 'paddles' in game_state:
        left_y = int(game_state['paddles']['0'])
        right_y = int(game_state['paddles']['1'])

        left_x = 20
        right_x = WIDTH - 52

        if PADDLE_IMG_LEFT:
            screen.blit(PADDLE_IMG_LEFT, (left_x, left_y))
        else:
            draw_rounded_paddle(screen, left_x, left_y, PADDLE_WIDTH, PADDLE_HEIGHT, GREEN, PADDLE_RADIUS)

        if PADDLE_IMG_RIGHT:
            screen.blit(PADDLE_IMG_RIGHT, (right_x, right_y))
        else:
            draw_rounded_paddle(screen, right_x, right_y, PADDLE_WIDTH, PADDLE_HEIGHT, MAGENTA, PADDLE_RADIUS)

    # М'яч + трейл + світіння
    if 'ball' in game_state:
        ball_x = int(game_state['ball']['x'])
        ball_y = int(game_state['ball']['y'])

        # Трейл
        ball_trail.add_position(ball_x, ball_y)
        ball_trail.draw(screen)

        # Легке світіння навколо м'яча
        glow_surface = pygame.Surface((BALL_RADIUS * 4, BALL_RADIUS * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surface, (*WHITE, 30), (BALL_RADIUS * 2, BALL_RADIUS * 2), BALL_RADIUS * 2)
        screen.blit(glow_surface, (ball_x - BALL_RADIUS * 2, ball_y - BALL_RADIUS * 2))

        # Спрайт м'яча (або коло, якщо немає спрайту)
        if BALL_IMG:
            screen.blit(BALL_IMG, (ball_x - BALL_RADIUS, ball_y - BALL_RADIUS))
        else:
            draw.circle(screen, WHITE, (ball_x, ball_y), BALL_RADIUS)

    # Оновлюємо прозорість трейлу
    ball_trail.update()

    # Роздільні рахунки зі спрайтовим фоном (ліво/право)
    if 'scores' in game_state:
        left_score = str(game_state['scores'][0])
        right_score = str(game_state['scores'][1])

        draw_score_box_sprite(screen, (WIDTH // 4, 40), left_score, font_main, SCORE_BG_LEFT_IMG, GOLD)
        draw_score_box_sprite(screen, (WIDTH * 3 // 4, 40), right_score, font_main, SCORE_BG_RIGHT_IMG, GOLD)

def draw_countdown(screen, countdown):
    """Відображення зворотного відліку"""
    screen.fill(BLACK)
    size = 72 + int(10 * (1 - (countdown % 1)))
    countdown_font = font.Font(None, size)
    countdown_text = countdown_font.render(str(int(countdown)), True, WHITE)
    text_rect = countdown_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
    screen.blit(countdown_text, text_rect)

def draw_winner(screen, is_winner):
    """Відображення екрану переможця"""
    screen.fill(DARKER_GRAY)
    message = "Ти переміг!" if is_winner else "Пощастить наступним разом!"
    win_text = font_win.render(message, True, GOLD)
    text_rect = win_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
    screen.blit(win_text, text_rect)
    restart_text = font_main.render('Натисни R для рестарту • Esc — меню', True, GOLD)
    restart_rect = restart_text.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 100))
    screen.blit(restart_text, restart_rect)

def draw_waiting(screen):
    """Відображення екрану очікування"""
    screen.fill(BLACK)
    dots = "." * ((pygame.time.get_ticks() // 500) % 4)
    waiting_text = font_main.render(f"Очікування гравців{dots}", True, WHITE)
    text_rect = waiting_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
    screen.blit(waiting_text, text_rect)

def play_sound(sound_event):
    """Програвання звуків"""
    if not sounds_enabled:
        return
    try:
        if sound_event == 'wall_hit':
            sound_wall.play()
        elif sound_event == 'platform_hit':
            sound_platform.play()
    except Exception:
        pass

# --- МЕНЮ ---
def draw_button(surface, rect, text, hovered=False):
    # прямокутник з радіусом
    color_bg = (40, 40, 40) if not hovered else (60, 60, 60)
    border = ACCENT if hovered else (120, 120, 120)
    pygame.draw.rect(surface, color_bg, rect, border_radius=14)
    pygame.draw.rect(surface, border, rect, width=2, border_radius=14)
    label = font_main.render(text, True, WHITE)
    surface.blit(label, label.get_rect(center=rect.center))

def draw_menu(screen):
    if BACKGROUND_IMG:
        screen.blit(BACKGROUND_IMG, (0, 0))
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0,0,0,140))
        screen.blit(overlay, (0,0))
    else:
        screen.fill(DARK_GRAY)

    title = font_title.render("Пінг-Понг", True, GOLD)
    screen.blit(title, title.get_rect(center=(WIDTH//2, HEIGHT//2 - 120)))

    play_rect = pygame.Rect(0, 0, 240, 64)
    exit_rect = pygame.Rect(0, 0, 240, 64)
    play_rect.center = (WIDTH//2, HEIGHT//2 + 10)
    exit_rect.center = (WIDTH//2, HEIGHT//2 + 90)

    mx, my = pygame.mouse.get_pos()
    draw_button(screen, play_rect, "Грати (Enter)", play_rect.collidepoint(mx, my))
    draw_button(screen, exit_rect, "Вийти (Esc)", exit_rect.collidepoint(mx, my))

    hint = font_small.render("W/S або ↑/↓ — керування платформаю", True, WHITE)
    screen.blit(hint, hint.get_rect(center=(WIDTH//2, HEIGHT - 40)))

    return play_rect, exit_rect

# --- ОСНОВНИЙ ІГРОВИЙ ЦИКЛ ---
def main():
    state = STATE_MENU
    client = None
    my_id = None
    receive_thread = None

    # Дані гри створюються лише при запуску гри
    game_state = None
    buffer = None
    you_winner = None
    ball_trail = None

    running = True
    while running:
        for e in event.get():
            if e.type == QUIT:
                running = False
            elif state == STATE_MENU:
                if e.type == pygame.KEYDOWN:
                    if e.key == K_RETURN:
                        # старт гри
                        state, client, my_id, game_state, buffer, you_winner, ball_trail, receive_thread = start_game()
                    elif e.key == K_ESCAPE:
                        running = False
                elif e.type == MOUSEBUTTONDOWN and e.button == 1:
                    play_rect, exit_rect = draw_menu(screen)  # для актуальних позицій
                    if play_rect.collidepoint(e.pos):
                        state, client, my_id, game_state, buffer, you_winner, ball_trail, receive_thread = start_game()
                    elif exit_rect.collidepoint(e.pos):
                        running = False

            elif state == STATE_GAME:
                if e.type == pygame.KEYDOWN:
                    if e.key == K_r and 'winner' in game_state:
                        send_command(client, "RESTART")
                        you_winner = None
                        ball_trail = BallTrail()  # Очищаємо трейл при рестарті
                    elif e.key == K_ESCAPE:
                        # повернення в меню
                        cleanup_connection(client, game_state)
                        state = STATE_MENU
                        client = None
                        my_id = None
                        receive_thread = None
                        game_state = None
                        buffer = None
                        you_winner = None
                        ball_trail = None

        if state == STATE_MENU:
            play_rect, exit_rect = draw_menu(screen)
            display.update()
            clock.tick(FPS)
            continue

        # ----------- СТАН: ГРА -----------
        # Стан підключення
        if game_state.get('disconnected', False):
            draw_waiting(screen)
            display.update()
            clock.tick(FPS)
        else:
            # Зворотний відлік
            if game_state.get('countdown', 0) > 0:
                draw_countdown(screen, game_state['countdown'])
                display.update()
                clock.tick(FPS)
            # Переможець
            elif 'winner' in game_state and game_state['winner'] is not None:
                if you_winner is None:
                    you_winner = (game_state['winner'] == my_id)
                draw_winner(screen, you_winner)
                display.update()
                clock.tick(FPS)
            # Гра або очікування
            else:
                if all(k in game_state for k in ['paddles', 'ball', 'scores']):
                    draw_game(screen, game_state, my_id, ball_trail)
                    if 'sound_event' in game_state and game_state['sound_event']:
                        play_sound(game_state['sound_event'])
                        game_state['sound_event'] = None
                else:
                    draw_waiting(screen)

                display.update()
                clock.tick(FPS)

                # Ввід: W/S та ↑/↓
                keys = key.get_pressed()
                if keys[K_w] or keys[K_UP]:
                    send_command(client, "UP")
                elif keys[K_s] or keys[K_DOWN]:
                    send_command(client, "DOWN")
                # Якщо сервер вимагає STOP при відпусканні — можна додати:
                # else:
                #     send_command(client, "STOP")

    # Завершення
    if state == STATE_GAME and client is not None:
        cleanup_connection(client, game_state)
    pygame.quit()
    sys.exit()

def start_game():
    """Ініціює підключення та структури стану гри, повертає потрібні змінні."""
    client, my_id = connect_to_server()
    game_state = {'running': True}
    buffer = {'data': ''}
    you_winner = None
    ball_trail = BallTrail()

    receive_thread = Thread(target=receive_data, args=(client, game_state, buffer), daemon=True)
    receive_thread.start()

    return STATE_GAME, client, my_id, game_state, buffer, you_winner, ball_trail, receive_thread

def cleanup_connection(client, game_state):
    """Акуратне закриття мережевого з’єднання та зупинка потоку."""
    try:
        game_state['running'] = False
    except Exception:
        pass
    try:
        client.close()
    except Exception:
        pass

if __name__ == "__main__":
    main()
