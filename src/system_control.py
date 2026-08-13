import os
import subprocess


def open_notepad(voice):

    voice.speak("Opening Notepad.")

    subprocess.Popen(
        ["notepad.exe"],
        shell=False
    )


def open_calculator(voice):

    voice.speak("Opening Calculator.")

    subprocess.Popen(
        ["calc.exe"],
        shell=False
    )


def open_command_prompt(voice):

    voice.speak("Opening Command Prompt.")

    subprocess.Popen(
        ["cmd.exe"],
        shell=False
    )


def open_powershell(voice):

    voice.speak("Opening PowerShell.")

    subprocess.Popen(
        ["powershell.exe"],
        shell=False
    )


def open_file_explorer(voice):

    voice.speak("Opening File Explorer.")

    subprocess.Popen(
        ["explorer.exe"],
        shell=False
    )


def open_settings(voice):

    voice.speak("Opening Windows Settings.")

    subprocess.Popen(
        ["cmd", "/c", "start", "ms-settings:"],
        shell=False
    )


def open_task_manager(voice):

    voice.speak("Opening Task Manager.")

    subprocess.Popen(
        ["taskmgr.exe"],
        shell=False
    )


def lock_computer(voice):

    voice.speak("Locking the computer.")

    os.system(
        "rundll32.exe user32.dll,LockWorkStation"
    )


def shutdown_computer(voice):

    voice.speak(
        "Shutting down the computer."
    )

    os.system(
        "shutdown /s /t 5"
    )


def restart_computer(voice):

    voice.speak(
        "Restarting the computer."
    )

    os.system(
        "shutdown /r /t 5"
    )


def handle_application(command, voice):
    """Try to handle a Windows application-launch command. Returns True if handled."""

    # NOTEPAD
    if "notepad" in command:
        open_notepad(voice)
        return True

    # CALCULATOR
    if "calculator" in command or "calc" in command:
        open_calculator(voice)
        return True

    # COMMAND PROMPT
    if "command prompt" in command or command == "cmd":
        open_command_prompt(voice)
        return True

    # POWERSHELL
    if "powershell" in command:
        open_powershell(voice)
        return True

    # FILE EXPLORER
    if "file explorer" in command or "explorer" in command:
        open_file_explorer(voice)
        return True

    # SETTINGS
    if "settings" in command:
        open_settings(voice)
        return True

    # TASK MANAGER
    if "task manager" in command:
        open_task_manager(voice)
        return True

    return False


def handle_system(command, voice):
    """Try to handle a system power command. Returns True if handled."""

    # LOCK COMPUTER
    if "lock computer" in command:
        lock_computer(voice)
        return True

    # SHUTDOWN
    if "shutdown computer" in command:
        shutdown_computer(voice)
        return True

    # RESTART
    if "restart computer" in command:
        restart_computer(voice)
        return True

    return False
