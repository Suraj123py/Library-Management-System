"""Library Management System - Python + MySQL (console based).

Setup:
    1. Start MySQL (for example with XAMPP)
    2. pip install mysql-connector-python
    3. python library.py
"""
import getpass
import os
from datetime import date, timedelta

import mysql.connector
from mysql.connector import Error

LOAN_DAYS = 14
FINE_PER_DAY = 2  # currency units per overdue day


def connect():
    host = input("MySQL host [localhost]: ").strip() or "localhost"
    user = input("MySQL user [root]: ").strip() or "root"
    password = getpass.getpass("MySQL password (press Enter if none): ")
    conn = mysql.connector.connect(host=host, user=user, password=password)
    cur = conn.cursor()
    schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
    with open(schema_path, encoding="utf-8") as f:
        statements = f.read().split(";")
    for stmt in statements:
        if stmt.strip():
            cur.execute(stmt)
    conn.database = "library_db"
    conn.commit()
    return conn


def ask_int(prompt):
    while True:
        try:
            return int(input(prompt))
        except ValueError:
            print("Please enter a number.")


# ---------- Books ----------
def add_book(conn):
    title = input("Title: ").strip()
    author = input("Author: ").strip()
    isbn = input("ISBN (optional): ").strip() or None
    copies = ask_int("Number of copies: ")
    if not title or not author or copies < 1:
        print("Title, author and at least 1 copy are required.")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO books (title, author, isbn, total_copies, available_copies) "
            "VALUES (%s, %s, %s, %s, %s)",
            (title, author, isbn, copies, copies),
        )
        conn.commit()
        print(f"Book added with ID {cur.lastrowid}.")
    except Error as e:
        conn.rollback()
        print("Could not add book:", e.msg)


def remove_book(conn):
    book_id = ask_int("Book ID to remove: ")
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM issues WHERE book_id = %s AND return_date IS NULL",
        (book_id,),
    )
    if cur.fetchone()[0] > 0:
        print("Cannot remove: copies of this book are currently issued.")
        return
    cur.execute("SELECT COUNT(*) FROM issues WHERE book_id = %s", (book_id,))
    if cur.fetchone()[0] > 0:
        print("Cannot remove: book has issue history. Keeping record intact.")
        return
    cur.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
    conn.commit()
    print("Book removed." if cur.rowcount else "No book with that ID.")


def list_books(conn, keyword=None):
    cur = conn.cursor()
    if keyword:
        like = f"%{keyword}%"
        cur.execute(
            "SELECT book_id, title, author, available_copies, total_copies "
            "FROM books WHERE title LIKE %s OR author LIKE %s",
            (like, like),
        )
    else:
        cur.execute(
            "SELECT book_id, title, author, available_copies, total_copies FROM books"
        )
    rows = cur.fetchall()
    if not rows:
        print("No books found.")
        return
    print(f"\n{'ID':<5}{'Title':<35}{'Author':<25}{'Available':<10}")
    for bid, title, author, avail, total in rows:
        print(f"{bid:<5}{title[:33]:<35}{author[:23]:<25}{avail}/{total}")


def search_books(conn):
    list_books(conn, input("Search title or author: ").strip())


# ---------- Members ----------
def register_member(conn):
    name = input("Name: ").strip()
    email = input("Email: ").strip() or None
    phone = input("Phone: ").strip() or None
    if not name:
        print("Name is required.")
        return
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO members (name, email, phone, joined_on) "
            "VALUES (%s, %s, %s, CURDATE())",
            (name, email, phone),
        )
        conn.commit()
        print(f"Member registered with ID {cur.lastrowid}.")
    except Error as e:
        conn.rollback()
        print("Could not register member:", e.msg)


def list_members(conn):
    cur = conn.cursor()
    cur.execute("SELECT member_id, name, email, phone FROM members")
    rows = cur.fetchall()
    if not rows:
        print("No members found.")
        return
    print(f"\n{'ID':<5}{'Name':<25}{'Email':<30}{'Phone'}")
    for mid, name, email, phone in rows:
        print(f"{mid:<5}{name:<25}{str(email):<30}{phone}")


# ---------- Issue / Return ----------
def issue_book(conn):
    book_id = ask_int("Book ID: ")
    member_id = ask_int("Member ID: ")
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT available_copies FROM books WHERE book_id = %s FOR UPDATE",
            (book_id,),
        )
        book = cur.fetchone()
        cur.execute("SELECT 1 FROM members WHERE member_id = %s", (member_id,))
        member = cur.fetchone()
        if not book or not member:
            print("Invalid book ID or member ID.")
            conn.rollback()
            return
        if book[0] < 1:
            print("No copies available right now.")
            conn.rollback()
            return
        today = date.today()
        due = today + timedelta(days=LOAN_DAYS)
        cur.execute(
            "INSERT INTO issues (book_id, member_id, issue_date, due_date) "
            "VALUES (%s, %s, %s, %s)",
            (book_id, member_id, today, due),
        )
        cur.execute(
            "UPDATE books SET available_copies = available_copies - 1 "
            "WHERE book_id = %s",
            (book_id,),
        )
        conn.commit()
        print(f"Issued. Due date: {due}")
    except Error as e:
        conn.rollback()
        print("Issue failed:", e.msg)


def return_book(conn):
    issue_id = ask_int("Issue ID: ")
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT book_id, due_date FROM issues "
            "WHERE issue_id = %s AND return_date IS NULL FOR UPDATE",
            (issue_id,),
        )
        row = cur.fetchone()
        if not row:
            print("No active issue with that ID.")
            conn.rollback()
            return
        book_id, due = row
        today = date.today()
        fine = max((today - due).days, 0) * FINE_PER_DAY
        cur.execute(
            "UPDATE issues SET return_date = %s, fine = %s WHERE issue_id = %s",
            (today, fine, issue_id),
        )
        cur.execute(
            "UPDATE books SET available_copies = available_copies + 1 "
            "WHERE book_id = %s",
            (book_id,),
        )
        conn.commit()
        print(f"Returned. Fine: {fine}" if fine else "Returned on time. No fine.")
    except Error as e:
        conn.rollback()
        print("Return failed:", e.msg)


def active_issues(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT i.issue_id, b.title, m.name, i.issue_date, i.due_date "
        "FROM issues i JOIN books b ON i.book_id = b.book_id "
        "JOIN members m ON i.member_id = m.member_id "
        "WHERE i.return_date IS NULL ORDER BY i.due_date"
    )
    rows = cur.fetchall()
    if not rows:
        print("No books currently issued.")
        return
    print(f"\n{'Issue':<7}{'Title':<30}{'Member':<20}{'Issued':<12}{'Due':<12}")
    for iid, title, name, issued, due in rows:
        flag = "  OVERDUE" if due < date.today() else ""
        print(f"{iid:<7}{title[:28]:<30}{name[:18]:<20}{issued!s:<12}{due!s:<12}{flag}")


MENU = """
===== Library Management System =====
1. Add book          6. Search books
2. Remove book       7. Issue book
3. List books        8. Return book
4. Register member   9. Currently issued books
5. List members      0. Exit
"""

ACTIONS = {
    "1": add_book, "2": remove_book, "3": list_books, "4": register_member,
    "5": list_members, "6": search_books, "7": issue_book, "8": return_book,
    "9": active_issues,
}


def main():
    try:
        conn = connect()
    except Error as e:
        print("Could not connect to MySQL:", e.msg)
        return
    except FileNotFoundError:
        print("schema.sql not found. Keep it in the same folder as library.py.")
        return
    while True:
        print(MENU)
        choice = input("Choose: ").strip()
        if choice == "0":
            break
        action = ACTIONS.get(choice)
        if action:
            action(conn)
        else:
            print("Invalid choice.")
    conn.close()


if __name__ == "__main__":
    main()