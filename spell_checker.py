import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import requests
import json
import subprocess
import os
import atexit
import sys


# === ГЛОБАЛЬНАЯ ПЕРЕМЕННАЯ (объявлена один раз на уровне модуля) ===
_server_process = None
LT_URL = "http://localhost:8081/v2/check"

def resource_path(relative_path):
    """ Получает путь к ресурсу — работает и в dev, и в PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def start_languagetool_server():
    global _server_process  # ← ОБЯЗАТЕЛЬНО В НАЧАЛЕ ФУНКЦИИ
    if _server_process is not None:
        return

    if os.name == 'nt':  # Windows
        java_exe = resource_path(os.path.join("jre", "bin", "java.exe"))
    else:  # macOS/Linux
        java_exe = "/opt/homebrew/opt/openjdk/bin/java"
        if not os.path.exists("java_exe"):
            java_exe = "/usr/bin/java"

    lt_jar = resource_path(os.path.join("languagetool", "languagetool-server.jar"))

    if not os.path.exists(java_exe):
        raise FileNotFoundError(f"Java not found at {java_exe}")
    if not os.path.exists(lt_jar):
        raise FileNotFoundError(f"LanguageTool JAR not found at {lt_jar}")

    _server_process = subprocess.Popen([
        java_exe, "-jar", lt_jar, "--port", "8081"
    ])

def stop_languagetool_server():
    global _server_process  # ← ТОЖЕ В НАЧАЛЕ
    if _server_process:
        _server_process.terminate()
        _server_process = None

# Запуск при старте
start_languagetool_server()
atexit.register(stop_languagetool_server)

def check_text_with_languagetool(text, language="en-US"):
    """
    Отправляет текст на локальный LanguageTool сервер и возвращает ошибки.
    """
    if not text.strip():
        return []

    try:
        response = requests.post(LT_URL, data={
            'text': text,
            'language': language,
            'disabledRules': ''  # можно добавить правила для отключения
        }, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result.get('matches', [])
    except requests.exceptions.RequestException as e:
        messagebox.showerror("Connection Error", f"Failed to connect to LanguageTool server:\n{str(e)}\n\nMake sure server is running on port 8081.")
        return []
    except json.JSONDecodeError:
        messagebox.showerror("Error", "Invalid response from LanguageTool server.")
        return []

def apply_replacements(text, matches):
    """
    Автоматически применяет первое предложенное исправление для каждой ошибки.
    """
    # Сортируем ошибки по позиции (с конца, чтобы смещения не ломались)
    sorted_matches = sorted(matches, key=lambda m: m['offset'], reverse=True)
    fixed_text = text

    for match in sorted_matches:
        offset = match['offset']
        length = match['length']
        replacements = match.get('replacements', [])
        if replacements:
            replacement = replacements[0]['value']  # первое исправление
            fixed_text = fixed_text[:offset] + replacement + fixed_text[offset + length:]
    return fixed_text

class SpellCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Advanced English Grammar & Spell Checker (Local Server)")
        self.root.geometry("1050x650")
        self.root.resizable(True, True)

        self.text_area = tk.Text(self.root, wrap="word", font=("Arial", 16), state="normal")
        self.text_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        self.text_area.bind("Control-v", self.paste_text)
        self.text_area.bind("Control-V", self.paste_text) # На случай Caps Lock

        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5)

        tk.Button(button_frame, text="Загрущить.txt файл", command=self.load_file).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Проверка грамматики и орфографии", command=self.check_text).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Автоматически все исправить", command=self.auto_fix_all).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Ручное исправление", command=self.manual_fix).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Очистить", command=self.clear_text).pack(side=tk.LEFT, padx=5)

        self.result_label = tk.Label(
            self.root,
            text="💡 Make sure LanguageTool server is running on port 8081!\n"
                 "Enter text and click 'Check Grammar & Spelling'",
            font=("Arial", 12),
            fg="gray",
            wraplength=800,
            justify="left"
        )
        self.result_label.pack(pady=12)

        self.last_matches = []

    def load_file(self):
        file_path = filedialog.askopenfilename(
            title="Select a .txt file",
            filetypes=[("Text files", "*.txt")]
        )
        if file_path:
            content = None
            for encoding in ['utf-8', 'cp1252', 'cp1251', 'iso-8859-1']:
                try:
                    with open(file_path, "r", encoding=encoding) as f:
                        content = f.read()
                    break  # успех — выходим
                except UnicodeDecodeError:
                    continue  # пробуем следующую кодировку

            if content is None:
                messagebox.showerror("Error", "Could not read file: unknown encoding.")
                return

            self.text_area.delete("1.0", tk.END)
            self.text_area.insert(tk.END, content)

    def check_text(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Input Needed", "Please enter text or load a file.")
            return

        matches = check_text_with_languagetool(text)
        self.last_matches = matches

        if not matches:
            self.result_label.config(text="✅ No issues found!", fg="green")
            return

        report = f"🔍 Found {len(matches)} issue(s):\n\n"
        for i, match in enumerate(matches[:10]):
            context = match['context']['text']
            offset_in_context = match['context']['offset']
            error_word = context[offset_in_context:offset_in_context + match['length']]
            replacements = [r['value'] for r in match.get('replacements', [])[:3]]
            sug_str = ", ".join(replacements) if replacements else "(no suggestions)"
            report += f"{i+1}. '{error_word}' → {sug_str}\n   • {match['message']}\n\n"

        if len(matches) > 10:
            report += f"... and {len(matches) - 10} more."

        self.result_label.config(text=report, fg="white", justify="left")

    def paste_text(self, event=None):
        try:
            # Всавить из буфера обмена
            self.text_area.insert(tk.INSERT, self.text_area.clipboard_get())
        except tk.TclError:
            pass  # Буфер пуст
        return "break"

    def auto_fix_all(self):
        text = self.text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("No Text", "No text to fix.")
            return
        if not self.last_matches:
            messagebox.showinfo("No Checked Errors", "Click 'Check' first.")
            return

        fixed = apply_replacements(text, self.last_matches)
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, fixed)
        self.result_label.config(text="✅ Auto-fix applied!", fg="green")
        self.last_matches = []

    def manual_fix(self):
        if not self.last_matches:
            messagebox.showinfo("No Checked Errors", "Click 'Check' first.")
            return

        text = self.text_area.get("1.0", tk.END).strip()
        fixed_text = text
        # Обрабатываем с конца, чтобы позиции не сбивались
        for match in sorted(self.last_matches, key=lambda m: m['offset'], reverse=True):
            error_word = text[match['offset']:match['offset'] + match['length']]
            replacements = [r['value'] for r in match.get('replacements', [])[:3]]
            if not replacements:
                continue

            choice = simpledialog.askstring(
                "Fix Error",
                f"Error: '{error_word}'\nSuggestions:\n" +
                "\n".join([f"{i+1}. {r}" for i, r in enumerate(replacements)]) +
                "\n\nEnter number or your fix:"
            )
            if choice is None:
                continue

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(replacements):
                    replacement = replacements[idx]
                else:
                    replacement = choice
            else:
                replacement = choice

            if replacement:
                start = match['offset']
                end = start + match['length']
                fixed_text = fixed_text[:start] + replacement + fixed_text[end:]

        self.text_area.delete("1.0", tk.END)
        self.text_area.insert(tk.END, fixed_text)
        self.result_label.config(text="✅ Manual fixes applied!", fg="green")
        self.last_matches = []

    def clear_text(self):
        self.text_area.delete("1.0", tk.END)
        self.result_label.config(text="Text cleared.", fg="gray")
        self.last_matches = []

if __name__ == "__main__":
    root = tk.Tk()
    app = SpellCheckerApp(root)
    root.mainloop()