import csv
import os
import re
import shutil
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from database import COURSE_FILE, DATA_FILE, load_json, save_json
from student_manager import calculate_grade


ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"
REPORT_DIR = "reports"
BACKUP_DIR = os.path.join("data", "backup")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SEMESTER_OPTIONS = tuple(f"Semester {number}" for number in range(2, 9))
DEPARTMENT_OPTIONS = ("FICT", "FABE", "FCMB", "FDI", "FBMG")
STATUS_FILTER_OPTIONS = ("All Statuses", "DISTINCTION", "PASS", "FAIL", "At Risk")
DEPARTMENT_FILTER_OPTIONS = ("All Departments",) + DEPARTMENT_OPTIONS
AT_RISK_SCORE = 50
AT_RISK_ATTENDANCE = 60


def as_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def score_text(value):
    number = float(as_number(value, 0) or 0)
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}"


def calculate_status(total):
    if total >= 80:
        return "DISTINCTION"
    if total >= 50:
        return "PASS"
    return "FAIL"


class LoginApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.authenticated = False
        self.title("EduTrack Sierra Leone Login")
        self.geometry("420x280")
        self.resizable(False, False)
        self.configure(bg="#f4f7f9")
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.front_job = None
        self.topmost_job = None
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("TButton", padding=(10, 6))

        self.build_login()
        self.center_window()
        self.front_job = self.after(100, self.bring_to_front)

    def build_login(self):
        container = tk.Frame(self, bg="#ffffff", padx=26, pady=24, highlightthickness=1)
        container.configure(highlightbackground="#d5dde5")
        container.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(
            container,
            text="Login Authentication",
            bg="#ffffff",
            fg="#202833",
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor="w")
        tk.Label(
            container,
            text="Use admin credentials to access EduTrack.",
            bg="#ffffff",
            fg="#607080",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 16))

        ttk.Label(container, text="Username").pack(anchor="w")
        username_entry = ttk.Entry(container, textvariable=self.username_var)
        username_entry.pack(fill="x", pady=(4, 10))

        ttk.Label(container, text="Password").pack(anchor="w")
        password_entry = ttk.Entry(container, textvariable=self.password_var, show="*")
        password_entry.pack(fill="x", pady=(4, 16))

        ttk.Button(container, text="Login", command=self.attempt_login).pack(fill="x")
        self.bind("<Return>", lambda _event: self.attempt_login())
        username_entry.focus_set()

    def attempt_login(self):
        if (
            self.username_var.get().strip() == ADMIN_USERNAME
            and self.password_var.get() == ADMIN_PASSWORD
        ):
            self.close_login(True)
            return
        messagebox.showerror("Access Denied", "Invalid username or password.")
        self.password_var.set("")

    def cancel(self):
        self.close_login(False)

    def close_login(self, authenticated):
        self.authenticated = authenticated
        for job_name in ("front_job", "topmost_job"):
            job = getattr(self, job_name)
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
                setattr(self, job_name, None)
        self.destroy()

    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def bring_to_front(self):
        self.front_job = None
        self.lift()
        self.attributes("-topmost", True)
        self.topmost_job = self.after(300, self.clear_topmost)

    def clear_topmost(self):
        self.topmost_job = None
        self.attributes("-topmost", False)


class EduTrackApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EduTrack Sierra Leone")
        self.geometry("1280x760")
        self.minsize(1120, 680)

        self.courses = self.load_courses()
        self.students = self.load_students()
        self.dark_mode = False
        self.theme = {}
        self.selected_student_id = None
        self.selected_course_code = None

        self.student_id_var = tk.StringVar()
        self.student_name_var = tk.StringVar()
        self.student_gender_var = tk.StringVar()
        self.student_phone_var = tk.StringVar()
        self.student_email_var = tk.StringVar()
        self.student_department_var = tk.StringVar()
        self.student_semester_var = tk.StringVar()
        self.student_course_var = tk.StringVar()
        self.student_ca_var = tk.StringVar()
        self.student_exam_var = tk.StringVar()
        self.student_total_var = tk.StringVar(value="0")
        self.student_grade_var = tk.StringVar(value="F")
        self.student_status_var = tk.StringVar(value="FAIL")
        self.student_present_var = tk.StringVar()
        self.student_absent_var = tk.StringVar()
        self.student_attendance_var = tk.StringVar(value="0")
        self.student_search_var = tk.StringVar()
        self.student_department_filter_var = tk.StringVar(value="All Departments")
        self.student_status_filter_var = tk.StringVar(value="All Statuses")
        self.course_code_var = tk.StringVar()
        self.course_name_var = tk.StringVar()

        self.student_ca_var.trace_add("write", lambda *_args: self.update_mark_preview())
        self.student_exam_var.trace_add("write", lambda *_args: self.update_mark_preview())
        self.student_present_var.trace_add(
            "write", lambda *_args: self.update_attendance_preview()
        )
        self.student_absent_var.trace_add(
            "write", lambda *_args: self.update_attendance_preview()
        )

        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.build_layout()
        self.apply_theme("light")
        self.refresh_all()

    def build_layout(self):
        self.header = tk.Frame(self, padx=18, pady=14)
        self.header.pack(fill="x")
        self.title_label = tk.Label(
            self.header,
            text="EDUTRACK SIERRA LEONE",
            font=("Segoe UI", 22, "bold"),
        )
        self.title_label.pack(anchor="w")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self.dashboard_tab = ttk.Frame(self.notebook, padding=18)
        self.students_tab = ttk.Frame(self.notebook, padding=18)
        self.courses_tab = ttk.Frame(self.notebook, padding=18)
        self.reports_tab = ttk.Frame(self.notebook, padding=18)
        self.analytics_tab = ttk.Frame(self.notebook, padding=18)
        self.settings_tab = ttk.Frame(self.notebook, padding=18)
        self.about_tab = ttk.Frame(self.notebook, padding=18)

        for label, frame in (
            ("Dashboard", self.dashboard_tab),
            ("Students", self.students_tab),
            ("Courses", self.courses_tab),
            ("Reports", self.reports_tab),
            ("Analytics", self.analytics_tab),
            ("Settings", self.settings_tab),
            ("About EduTrack Sierra Leone", self.about_tab),
        ):
            self.notebook.add(frame, text=label)

        self.build_dashboard()
        self.build_students_page()
        self.build_courses_page()
        self.build_reports_page()
        self.build_analytics_page()
        self.build_settings_page()
        self.build_about_page()
        self.notebook.bind("<<NotebookTabChanged>>", self.handle_tab_change)

    def build_dashboard(self):
        self.dashboard_cards = {}
        card_grid = ttk.Frame(self.dashboard_tab)
        card_grid.pack(fill="x")
        card_grid.columnconfigure((0, 1, 2), weight=1, uniform="cards")

        for index, label in enumerate(
            (
                "Total Students",
                "Average Score",
                "Pass Rate",
                "Distinctions",
                "At Risk",
                "Top Student",
            )
        ):
            card = tk.Frame(card_grid, padx=18, pady=18, highlightthickness=1)
            card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=7, pady=7)
            card_title = tk.Label(card, text=label, font=("Segoe UI", 10, "bold"))
            card_title.pack(anchor="w")
            card_value = tk.Label(card, text="-", font=("Segoe UI", 21, "bold"))
            card_value.pack(anchor="w", pady=(12, 0))
            self.dashboard_cards[label] = (card, card_title, card_value)

        summary = ttk.LabelFrame(self.dashboard_tab, text="Student Summary", padding=12)
        summary.pack(fill="both", expand=True, pady=(18, 0))
        summary.rowconfigure(0, weight=1)
        summary.columnconfigure(0, weight=1)

        self.dashboard_tree = ttk.Treeview(
            summary,
            columns=(
                "id",
                "name",
                "department",
                "semester",
                "course",
                "total",
                "grade",
                "status",
                "attendance",
            ),
            show="headings",
            height=12,
        )
        self.configure_student_tree(self.dashboard_tree)
        self.dashboard_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(summary, orient="vertical", command=self.dashboard_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.dashboard_tree.configure(yscrollcommand=scroll.set)

    def build_students_page(self):
        self.students_tab.columnconfigure(1, weight=1)
        self.students_tab.rowconfigure(1, weight=1)

        form = ttk.LabelFrame(self.students_tab, text="Student Profile", padding=10)
        form.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 14))
        form.columnconfigure(1, weight=1)

        self.add_labeled_entry(form, "Student ID", self.student_id_var, 0)
        self.add_labeled_entry(form, "Name", self.student_name_var, 1)
        self.add_labeled_combo(
            form,
            "Gender",
            self.student_gender_var,
            ("Male", "Female", "Other"),
            2,
        )
        self.add_labeled_entry(form, "Phone", self.student_phone_var, 3)
        self.add_labeled_entry(form, "Email", self.student_email_var, 4)
        self.add_labeled_combo(
            form,
            "Department",
            self.student_department_var,
            DEPARTMENT_OPTIONS,
            5,
        )
        self.add_labeled_combo(
            form,
            "Semester",
            self.student_semester_var,
            SEMESTER_OPTIONS,
            6,
        )
        self.course_combo = self.add_labeled_combo(
            form, "Course", self.student_course_var, self.course_options(), 7
        )
        self.add_labeled_entry(form, "CA Mark", self.student_ca_var, 8)
        self.add_labeled_entry(form, "Exam Mark", self.student_exam_var, 9)
        self.add_readonly_entry(form, "Total", self.student_total_var, 10)
        self.add_readonly_entry(form, "Grade", self.student_grade_var, 11)
        self.add_readonly_entry(form, "Status", self.student_status_var, 12)
        self.add_labeled_entry(form, "Present Days", self.student_present_var, 13)
        self.add_labeled_entry(form, "Absent Days", self.student_absent_var, 14)
        self.add_readonly_entry(form, "Attendance %", self.student_attendance_var, 15)

        button_frame = ttk.Frame(form)
        button_frame.grid(row=16, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        button_frame.columnconfigure((0, 1), weight=1)

        ttk.Button(button_frame, text="Add Student", command=self.add_student).grid(
            row=0, column=0, sticky="ew", padx=(0, 5), pady=3
        )
        ttk.Button(button_frame, text="Update Student", command=self.update_student).grid(
            row=0, column=1, sticky="ew", padx=(5, 0), pady=3
        )
        ttk.Button(button_frame, text="Delete Student", command=self.delete_student).grid(
            row=1, column=0, sticky="ew", padx=(0, 5), pady=3
        )
        ttk.Button(button_frame, text="Clear", command=self.clear_student_form).grid(
            row=1, column=1, sticky="ew", padx=(5, 0), pady=3
        )
        ttk.Button(button_frame, text="View Profile", command=self.show_selected_profile).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=3
        )

        search_frame = ttk.Frame(self.students_tab)
        search_frame.grid(row=0, column=1, sticky="ew")
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search Student").grid(row=0, column=0, padx=(0, 8))
        search_entry = ttk.Entry(search_frame, textvariable=self.student_search_var)
        search_entry.grid(row=0, column=1, sticky="ew")
        search_entry.bind("<Return>", lambda _event: self.refresh_students_table())
        ttk.Button(search_frame, text="Search", command=self.refresh_students_table).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(search_frame, text="Reset", command=self.reset_student_filters).grid(
            row=0, column=3, padx=(8, 0)
        )
        ttk.Label(search_frame, text="Department").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        department_filter = ttk.Combobox(
            search_frame,
            textvariable=self.student_department_filter_var,
            values=DEPARTMENT_FILTER_OPTIONS,
            state="readonly",
            width=20,
        )
        department_filter.grid(row=1, column=1, sticky="w", pady=(8, 0))
        ttk.Label(search_frame, text="Status").grid(
            row=1, column=2, sticky="e", padx=(8, 8), pady=(8, 0)
        )
        status_filter = ttk.Combobox(
            search_frame,
            textvariable=self.student_status_filter_var,
            values=STATUS_FILTER_OPTIONS,
            state="readonly",
            width=18,
        )
        status_filter.grid(row=1, column=3, sticky="ew", pady=(8, 0))
        department_filter.bind("<<ComboboxSelected>>", lambda _event: self.refresh_students_table())
        status_filter.bind("<<ComboboxSelected>>", lambda _event: self.refresh_students_table())

        table_frame = ttk.LabelFrame(
            self.students_tab, text="Students Treeview Table", padding=10
        )
        table_frame.grid(row=1, column=1, sticky="nsew", pady=(12, 0))
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.student_tree = ttk.Treeview(
            table_frame,
            columns=(
                "id",
                "name",
                "gender",
                "phone",
                "email",
                "department",
                "semester",
                "course",
                "ca",
                "exam",
                "total",
                "grade",
                "status",
                "present_days",
                "absent_days",
                "attendance",
            ),
            show="headings",
            selectmode="browse",
        )
        self.configure_student_tree(self.student_tree)
        self.student_tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.student_tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.student_tree.xview
        )
        xscroll.grid(row=1, column=0, sticky="ew")
        self.student_tree.configure(
            yscrollcommand=yscroll.set, xscrollcommand=xscroll.set
        )
        self.student_tree.bind("<<TreeviewSelect>>", self.fill_student_form)

    def build_courses_page(self):
        self.courses_tab.columnconfigure(1, weight=1)
        self.courses_tab.rowconfigure(0, weight=1)

        form = ttk.LabelFrame(self.courses_tab, text="Course Details", padding=12)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 14))
        form.columnconfigure(1, weight=1)
        self.add_labeled_entry(form, "Course Code", self.course_code_var, 0)
        self.add_labeled_entry(form, "Course Name", self.course_name_var, 1)

        button_frame = ttk.Frame(form)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        button_frame.columnconfigure((0, 1), weight=1)
        ttk.Button(button_frame, text="Add Course", command=self.add_course).grid(
            row=0, column=0, sticky="ew", padx=(0, 6), pady=4
        )
        ttk.Button(button_frame, text="Edit Course", command=self.update_course).grid(
            row=0, column=1, sticky="ew", padx=(6, 0), pady=4
        )
        ttk.Button(button_frame, text="Delete Course", command=self.delete_course).grid(
            row=1, column=0, sticky="ew", padx=(0, 6), pady=4
        )
        ttk.Button(button_frame, text="Clear", command=self.clear_course_form).grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=4
        )

        table_frame = ttk.LabelFrame(
            self.courses_tab, text="Courses Treeview Table", padding=10
        )
        table_frame.grid(row=0, column=1, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        self.course_tree = ttk.Treeview(
            table_frame, columns=("code", "name"), show="headings", selectmode="browse"
        )
        self.course_tree.heading("code", text="Code")
        self.course_tree.heading("name", text="Course Name")
        self.course_tree.column("code", width=140, minwidth=100, anchor="w")
        self.course_tree.column("name", width=420, minwidth=180, anchor="w")
        self.course_tree.grid(row=0, column=0, sticky="nsew")
        course_scroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.course_tree.yview
        )
        course_scroll.grid(row=0, column=1, sticky="ns")
        self.course_tree.configure(yscrollcommand=course_scroll.set)
        self.course_tree.bind("<<TreeviewSelect>>", self.fill_course_form)

    def build_reports_page(self):
        self.reports_tab.columnconfigure(0, weight=1)

        actions = ttk.LabelFrame(self.reports_tab, text="Reports", padding=18)
        actions.grid(row=0, column=0, sticky="ew")
        actions.columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="report-buttons")

        ttk.Button(
            actions, text="Generate TXT Report", command=self.generate_txt_report
        ).grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        ttk.Button(actions, text="Export CSV", command=self.export_csv_report).grid(
            row=0, column=1, sticky="ew", padx=6, pady=6
        )
        ttk.Button(actions, text="Backup Database", command=self.backup_database).grid(
            row=0, column=2, sticky="ew", padx=6, pady=6
        )
        ttk.Button(actions, text="Student Ranking", command=self.show_student_ranking).grid(
            row=0, column=3, sticky="ew", padx=6, pady=6
        )
        ttk.Button(actions, text="At Risk Students", command=self.show_at_risk_students).grid(
            row=0, column=4, sticky="ew", padx=6, pady=6
        )

        self.report_status = tk.Text(self.reports_tab, height=16, wrap="word")
        self.report_status.grid(row=1, column=0, sticky="nsew", pady=(18, 0))
        self.reports_tab.rowconfigure(1, weight=1)
        self.write_report_status("Reports will be saved in the reports folder.")

    def build_analytics_page(self):
        self.analytics_tab.columnconfigure((0, 1), weight=1, uniform="charts")
        self.analytics_tab.rowconfigure((0, 1), weight=1, uniform="charts")

        self.grade_canvas = self.add_chart_canvas(
            self.analytics_tab, "Grade Distribution Chart", 0, 0
        )
        self.pass_canvas = self.add_chart_canvas(
            self.analytics_tab, "Pass vs Fail Chart", 0, 1
        )
        self.attendance_canvas = self.add_chart_canvas(
            self.analytics_tab, 
            "Attendance Chart", 
            1, 
            0,
            columnspan=2
        )

        for canvas in (
            self.grade_canvas,
            self.pass_canvas,
            self.attendance_canvas
        ):
            canvas.bind("<Configure>", lambda _event: self.draw_all_charts())

    def build_settings_page(self):
        panel = ttk.LabelFrame(self.settings_tab, text="Theme", padding=18)
        panel.pack(anchor="nw", fill="x")
        ttk.Button(panel, text="Dark Mode", command=lambda: self.apply_theme("dark")).pack(
            side="left", padx=(0, 10)
        )
        ttk.Button(panel, text="Light Mode", command=lambda: self.apply_theme("light")).pack(
            side="left"
        )

    def build_about_page(self):
        panel = tk.Frame(self.about_tab, padx=34, pady=30, highlightthickness=1)
        panel.pack(fill="both", expand=True)
        self.about_panel = panel

        self.about_labels = []
        lines =  (
        ("About EduTrack Sierra Leone", ("Segoe UI", 24, "bold")),
        ("Developed for:", ("Segoe UI", 12, "bold")),
        ("PROG103 Principles of Structured Programming", ("Segoe UI", 15)),
        ("SDG 4: Quality Education", ("Segoe UI", 15)),
        ("Project Team", ("Segoe UI", 16, "bold")),
        ("Michael Tucker", ("Segoe UI", 14, "bold")),
        ("Lead Developer & System Architect", ("Segoe UI", 12)),
        ("Maria Williams", ("Segoe UI", 14, "bold")),
        ("Documentation & Authentiction js", ("Segoe UI", 12)),
        ("Andrew Bai Conteh", ("Segoe UI", 14, "bold")),
        ("System Analysis & Validation", ("Segoe UI", 12)),
    )
        for text, font in lines:
            label = tk.Label(panel, text=text, font=font, anchor="w")
            label.pack(anchor="w", pady=(0, 14))
            self.about_labels.append(label)

    def add_labeled_entry(self, parent, label, variable, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=30)
        entry.grid(row=row, column=1, sticky="ew", pady=3, padx=(10, 0))
        return entry

    def add_readonly_entry(self, parent, label, variable, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=variable, width=30, state="readonly")
        entry.grid(row=row, column=1, sticky="ew", pady=3, padx=(10, 0))
        return entry

    def add_labeled_combo(self, parent, label, variable, values, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        combo = ttk.Combobox(
            parent, textvariable=variable, values=tuple(values), width=27, state="readonly"
        )
        combo.grid(row=row, column=1, sticky="ew", pady=3, padx=(10, 0))
        return combo

    def add_chart_canvas(self, parent, title, row, column, columnspan=1):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.grid(
            row=row,
            column=column,
            columnspan=columnspan,
            sticky="nsew",
            padx=7,
            pady=7,
        )
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        canvas = tk.Canvas(frame, height=220, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        return canvas

    def configure_student_tree(self, tree):
        definitions = {
            "id": ("ID", 120),
            "name": ("Name", 190),
            "gender": ("Gender", 90),
            "phone": ("Phone", 120),
            "email": ("Email", 190),
            "department": ("Department", 110),
            "semester": ("Semester", 100),
            "course": ("Course", 220),
            "ca": ("CA", 70),
            "exam": ("Exam", 80),
            "total": ("Total", 80),
            "grade": ("Grade", 80),
            "status": ("Status", 120),
            "present_days": ("Present Days", 110),
            "absent_days": ("Absent Days", 110),
            "attendance": ("Attendance %", 120),
        }
        for column in tree["columns"]:
            label, width = definitions[column]
            tree.heading(column, text=label)
            tree.column(column, width=width, minwidth=70, anchor="w")

    def load_students(self):
        students = []
        for student in load_json(DATA_FILE):
            ca = as_number(student.get("ca"), None)
            exam = as_number(student.get("exam"), None)
            total = as_number(student.get("total"), 0)
            if ca is None and exam is None:
                ca = total
                exam = 0
            elif ca is None:
                ca = 0
            elif exam is None:
                exam = 0
            total = ca + exam

            attendance = as_number(student.get("attendance"), 100)
            present_days = as_number(student.get("present_days"), None)
            absent_days = as_number(student.get("absent_days"), None)
            if present_days is None and absent_days is None:
                present_days = attendance
                absent_days = max(0, 100 - attendance)
            elif present_days is None:
                present_days = 0
            elif absent_days is None:
                absent_days = 0
            attendance = self.calculate_attendance(present_days, absent_days, attendance)

            course_code = str(student.get("course_code", "")).strip()
            course_name = str(student.get("course_name", "")).strip()
            if not course_name and course_code:
                course_name = self.course_name_for_code(course_code)

            students.append(
                {
                    "id": str(student.get("id", "")).strip(),
                    "name": str(student.get("name", "")).strip(),
                    "gender": str(student.get("gender", "")).strip(),
                    "phone": str(student.get("phone", "")).strip(),
                    "email": str(student.get("email", "")).strip(),
                    "department": str(student.get("department", "")).strip().upper(),
                    "semester": self.normalize_semester(
                        student.get("semester") or student.get("level", "")
                    ),
                    "course_code": course_code,
                    "course_name": course_name,
                    "ca": ca,
                    "exam": exam,
                    "total": total,
                    "grade": calculate_grade(total),
                    "status": calculate_status(total),
                    "present_days": present_days,
                    "absent_days": absent_days,
                    "attendance": attendance,
                }
            )
        return students

    def load_courses(self):
        courses = []
        for course in load_json(COURSE_FILE):
            courses.append(
                {
                    "code": str(course.get("code", "")).strip().upper(),
                    "name": str(course.get("name", "")).strip(),
                }
            )
        return courses

    def save_students(self):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        for student in self.students:
            student.pop("level", None)
            student["department"] = str(student.get("department", "")).strip().upper()
            student["semester"] = self.normalize_semester(student.get("semester", ""))
            student["total"] = as_number(student.get("ca")) + as_number(student.get("exam"))
            student["grade"] = calculate_grade(student["total"])
            student["status"] = calculate_status(student["total"])
            student["attendance"] = self.calculate_attendance(
                student.get("present_days"), student.get("absent_days")
            )
        save_json(DATA_FILE, self.students)

    def save_courses(self):
        os.makedirs(os.path.dirname(COURSE_FILE), exist_ok=True)
        save_json(COURSE_FILE, self.courses)

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_students_table()
        self.refresh_courses_table()
        self.refresh_course_selector()
        self.draw_all_charts()

    def refresh_dashboard(self):
        total_students = len(self.students)
        scores = [as_number(student.get("total")) for student in self.students]
        average_score = sum(scores) / total_students if total_students else 0
        passed = len([student for student in self.students if student["status"] != "FAIL"])
        pass_rate = (passed / total_students * 100) if total_students else 0
        distinctions = len(
            [student for student in self.students if student["status"] == "DISTINCTION"]
        )
        at_risk = len(self.at_risk_students())
        top_student = max(
            self.students, key=lambda student: as_number(student.get("total")), default=None
        )

        values = {
            "Total Students": str(total_students),
            "Average Score": f"{average_score:.1f}",
            "Pass Rate": f"{pass_rate:.1f}%",
            "Distinctions": str(distinctions),
            "At Risk": str(at_risk),
            "Top Student": top_student["name"] if top_student else "-",
        }

        for label, value in values.items():
            _card, _title, value_label = self.dashboard_cards[label]
            value_label.configure(text=value)

        self.populate_student_tree(self.dashboard_tree, self.students)

    def at_risk_students(self):
        return [student for student in self.students if self.is_at_risk(student)]

    def is_at_risk(self, student):
        return (
            as_number(student.get("total"), 0) < AT_RISK_SCORE
            or as_number(student.get("attendance"), 0) < AT_RISK_ATTENDANCE
        )

    def risk_reason(self, student):
        reasons = []
        if as_number(student.get("total"), 0) < AT_RISK_SCORE:
            reasons.append("Low total")
        if as_number(student.get("attendance"), 0) < AT_RISK_ATTENDANCE:
            reasons.append("Low attendance")
        return "; ".join(reasons)

    def refresh_students_table(self):
        query = self.student_search_var.get().strip().lower()
        department = self.student_department_filter_var.get()
        status = self.student_status_filter_var.get()
        filtered = self.students
        if query:
            filtered = [
                student
                for student in filtered
                if query in student["id"].lower()
                or query in student["name"].lower()
                or query in student["gender"].lower()
                or query in student["email"].lower()
                or query in student["department"].lower()
                or query in student["semester"].lower()
                or query in self.student_course_text(student).lower()
                or query in student["grade"].lower()
                or query in student["status"].lower()
            ]
        if department != "All Departments":
            filtered = [
                student for student in filtered if student["department"] == department
            ]
        if status == "At Risk":
            filtered = [student for student in filtered if self.is_at_risk(student)]
        elif status != "All Statuses":
            filtered = [student for student in filtered if student["status"] == status]
        self.populate_student_tree(self.student_tree, filtered)

    def reset_student_filters(self):
        self.student_search_var.set("")
        self.student_department_filter_var.set("All Departments")
        self.student_status_filter_var.set("All Statuses")
        self.refresh_students_table()

    def populate_student_tree(self, tree, students):
        for item in tree.get_children():
            tree.delete(item)
        for student in students:
            values_by_column = {
                "id": student["id"],
                "name": student["name"],
                "gender": student["gender"],
                "phone": student["phone"],
                "email": student["email"],
                "department": student["department"],
                "semester": student["semester"],
                "course": self.student_course_text(student),
                "ca": score_text(student["ca"]),
                "exam": score_text(student["exam"]),
                "total": score_text(student["total"]),
                "grade": student["grade"],
                "status": student["status"],
                "present_days": score_text(student["present_days"]),
                "absent_days": score_text(student["absent_days"]),
                "attendance": score_text(student["attendance"]),
            }
            tree.insert(
                "",
                "end",
                iid=student["id"] if tree is self.student_tree else None,
                values=tuple(values_by_column[column] for column in tree["columns"]),
            )

    def refresh_courses_table(self):
        for item in self.course_tree.get_children():
            self.course_tree.delete(item)
        for course in self.courses:
            self.course_tree.insert(
                "", "end", iid=course["code"], values=(course["code"], course["name"])
            )

    def refresh_course_selector(self):
        if hasattr(self, "course_combo"):
            values = self.course_options()
            self.course_combo.configure(values=values)
            if self.student_course_var.get() and self.student_course_var.get() not in values:
                self.student_course_var.set("")

    def add_student(self):
        student = self.student_from_form()
        if student is None:
            return
        if self.find_student(student["id"]):
            messagebox.showerror("Duplicate Student", "A student with this ID already exists.")
            return
        self.students.append(student)
        self.save_students()
        self.clear_student_form()
        self.refresh_all()
        messagebox.showinfo("Saved", "Student added successfully.")

    def update_student(self):
        student = self.student_from_form()
        if student is None:
            return
        target_id = self.selected_student_id or student["id"]
        existing = self.find_student(target_id)
        if not existing:
            messagebox.showerror("Missing Student", "Select a student or enter an existing ID.")
            return
        if student["id"] != target_id and self.find_student(student["id"]):
            messagebox.showerror("Duplicate Student", "A student with this ID already exists.")
            return
        existing.update(student)
        self.selected_student_id = student["id"]
        self.save_students()
        self.refresh_all()
        messagebox.showinfo("Saved", "Student updated successfully.")

    def delete_student(self):
        sid = self.selected_student_id or self.student_id_var.get().strip()
        if not sid:
            selection = self.student_tree.selection()
            sid = selection[0] if selection else ""
        if not sid:
            messagebox.showerror("Missing Student", "Select a student to delete.")
            return
        student = self.find_student(sid)
        if not student:
            messagebox.showerror("Missing Student", "Student not found.")
            return
        if not messagebox.askyesno("Delete Student", f"Delete {student['name']}?"):
            return
        self.students = [item for item in self.students if item["id"] != sid]
        self.save_students()
        self.clear_student_form()
        self.refresh_all()

    def student_from_form(self):
        sid = self.student_id_var.get().strip()
        name = self.student_name_var.get().strip()
        gender = self.student_gender_var.get().strip()
        phone = self.student_phone_var.get().strip()
        email = self.student_email_var.get().strip()
        department = self.student_department_var.get().strip().upper()
        semester = self.student_semester_var.get().strip()
        course_option = self.student_course_var.get().strip()

        required = (
            (sid, "Student ID"),
            (name, "Name"),
            (gender, "Gender"),
            (phone, "Phone"),
            (email, "Email"),
            (department, "Department"),
            (semester, "Semester"),
            (course_option, "Course"),
            (self.student_ca_var.get().strip(), "CA Mark"),
            (self.student_exam_var.get().strip(), "Exam Mark"),
            (self.student_present_var.get().strip(), "Present Days"),
            (self.student_absent_var.get().strip(), "Absent Days"),
        )
        missing = [label for value, label in required if not value]
        if missing:
            messagebox.showerror("Empty Fields", "Please fill: " + ", ".join(missing))
            return None
        if not EMAIL_PATTERN.match(email):
            messagebox.showerror("Invalid Email", "Enter a valid email address.")
            return None
        if department not in DEPARTMENT_OPTIONS:
            messagebox.showerror("Invalid Department", "Select a valid department.")
            return None
        if semester not in SEMESTER_OPTIONS:
            messagebox.showerror("Invalid Semester", "Select a valid semester.")
            return None

        ca = self.valid_number(self.student_ca_var.get(), "CA Mark")
        exam = self.valid_number(self.student_exam_var.get(), "Exam Mark")
        present_days = self.valid_number(self.student_present_var.get(), "Present Days")
        absent_days = self.valid_number(self.student_absent_var.get(), "Absent Days")
        if None in (ca, exam, present_days, absent_days):
            return None
        if ca < 0 or exam < 0:
            messagebox.showerror("Invalid Marks", "Marks cannot be negative.")
            return None
        if ca > 100 or exam > 100:
            messagebox.showerror("Invalid Marks", "Marks cannot be above 100.")
            return None
        total = ca + exam
        if total > 100:
            messagebox.showerror(
                "Invalid Total", "CA + Exam must not be above 100 marks."
            )
            return None
        if present_days < 0 or absent_days < 0:
            messagebox.showerror("Invalid Attendance", "Attendance days cannot be negative.")
            return None
        if present_days + absent_days <= 0:
            messagebox.showerror(
                "Invalid Attendance", "Present days plus absent days must be above 0."
            )
            return None

        course_code, course_name = self.course_from_option(course_option)
        grade = calculate_grade(total)
        status = calculate_status(total)
        attendance = self.calculate_attendance(present_days, absent_days)

        return {
            "id": sid,
            "name": name,
            "gender": gender,
            "phone": phone,
            "email": email,
            "department": department,
            "semester": semester,
            "course_code": course_code,
            "course_name": course_name,
            "ca": ca,
            "exam": exam,
            "total": total,
            "grade": grade,
            "status": status,
            "present_days": present_days,
            "absent_days": absent_days,
            "attendance": attendance,
        }

    def valid_number(self, raw_value, label):
        number = as_number(raw_value, None)
        if number is None:
            messagebox.showerror("Invalid Number", f"{label} must be a number.")
        return number

    def fill_student_form(self, _event):
        selection = self.student_tree.selection()
        if not selection:
            return
        student = self.find_student(selection[0])
        if not student:
            return
        self.selected_student_id = student["id"]
        self.student_id_var.set(student["id"])
        self.student_name_var.set(student["name"])
        self.student_gender_var.set(student["gender"])
        self.student_phone_var.set(student["phone"])
        self.student_email_var.set(student["email"])
        self.student_department_var.set(student["department"])
        self.student_semester_var.set(student["semester"])
        self.student_course_var.set(self.student_course_text(student))
        self.student_ca_var.set(score_text(student["ca"]))
        self.student_exam_var.set(score_text(student["exam"]))
        self.student_total_var.set(score_text(student["total"]))
        self.student_grade_var.set(student["grade"])
        self.student_status_var.set(student["status"])
        self.student_present_var.set(score_text(student["present_days"]))
        self.student_absent_var.set(score_text(student["absent_days"]))
        self.student_attendance_var.set(score_text(student["attendance"]))

    def clear_student_form(self):
        self.selected_student_id = None
        self.student_id_var.set("")
        self.student_name_var.set("")
        self.student_gender_var.set("")
        self.student_phone_var.set("")
        self.student_email_var.set("")
        self.student_department_var.set("")
        self.student_semester_var.set("")
        self.student_course_var.set("")
        self.student_ca_var.set("")
        self.student_exam_var.set("")
        self.student_total_var.set("0")
        self.student_grade_var.set("F")
        self.student_status_var.set("FAIL")
        self.student_present_var.set("")
        self.student_absent_var.set("")
        self.student_attendance_var.set("0")
        self.student_tree.selection_remove(self.student_tree.selection())

    def find_student(self, sid):
        return next((student for student in self.students if student["id"] == sid), None)

    def add_course(self):
        course = self.course_from_form()
        if course is None:
            return
        if self.find_course(course["code"]):
            messagebox.showerror("Duplicate Course", "A course with this code already exists.")
            return
        self.courses.append(course)
        self.save_courses()
        self.clear_course_form()
        self.refresh_courses_table()
        self.refresh_course_selector()
        messagebox.showinfo("Saved", "Course added successfully.")

    def update_course(self):
        course = self.course_from_form()
        if course is None:
            return
        target_code = self.selected_course_code or course["code"]
        existing = self.find_course(target_code)
        if not existing:
            messagebox.showerror("Missing Course", "Select a course or enter an existing code.")
            return
        if course["code"] != target_code and self.find_course(course["code"]):
            messagebox.showerror("Duplicate Course", "A course with this code already exists.")
            return
        existing.update(course)
        self.sync_student_course(target_code, course)
        self.selected_course_code = course["code"]
        self.save_courses()
        self.save_students()
        self.refresh_all()
        messagebox.showinfo("Saved", "Course updated successfully.")

    def delete_course(self):
        code = self.selected_course_code or self.course_code_var.get().strip().upper()
        if not code:
            selection = self.course_tree.selection()
            code = selection[0] if selection else ""
        if not code:
            messagebox.showerror("Missing Course", "Select a course to delete.")
            return
        course = self.find_course(code)
        if not course:
            messagebox.showerror("Missing Course", "Course not found.")
            return
        if not messagebox.askyesno("Delete Course", f"Delete {course['name']}?"):
            return
        self.courses = [item for item in self.courses if item["code"] != code]
        self.save_courses()
        self.clear_course_form()
        self.refresh_all()

    def course_from_form(self):
        code = self.course_code_var.get().strip().upper()
        name = self.course_name_var.get().strip()
        if not code or not name:
            messagebox.showerror("Missing Details", "Course code and name are required.")
            return None
        return {"code": code, "name": name}

    def fill_course_form(self, _event):
        selection = self.course_tree.selection()
        if not selection:
            return
        course = self.find_course(selection[0])
        if not course:
            return
        self.selected_course_code = course["code"]
        self.course_code_var.set(course["code"])
        self.course_name_var.set(course["name"])

    def clear_course_form(self):
        self.selected_course_code = None
        self.course_code_var.set("")
        self.course_name_var.set("")
        self.course_tree.selection_remove(self.course_tree.selection())

    def find_course(self, code):
        return next((course for course in self.courses if course["code"] == code), None)

    def generate_txt_report(self):
        os.makedirs(REPORT_DIR, exist_ok=True)
        filename = os.path.join(REPORT_DIR, f"student_report_{self.timestamp()}.txt")
        ranked = self.ranked_students()

        with open(filename, "w", encoding="utf-8") as report:
            report.write("EDUTRACK SIERRA LEONE\n")
            report.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            report.write(f"Total Students: {len(self.students)}\n")
            report.write(f"Average Score: {self.average_score():.1f}\n")
            report.write(f"Pass Rate: {self.pass_rate():.1f}%\n\n")
            report.write("Student Ranking\n")
            for rank, student in enumerate(ranked, start=1):
                report.write(
                    f"{rank}. {student['id']} - {student['name']} - "
                    f"{student['department']} - {student['semester']} - "
                    f"{self.student_course_text(student)} - CA {score_text(student['ca'])}, "
                    f"Exam {score_text(student['exam'])}, Total {score_text(student['total'])}, "
                    f"Grade {student['grade']}, Status {student['status']}, "
                    f"Attendance {score_text(student['attendance'])}%\n"
                )

        self.write_report_status(f"TXT report generated:\n{filename}")
        messagebox.showinfo("Report Generated", filename)

    def export_csv_report(self):
        os.makedirs(REPORT_DIR, exist_ok=True)
        filename = os.path.join(REPORT_DIR, f"students_{self.timestamp()}.csv")
        with open(filename, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "ID",
                    "Name",
                    "Gender",
                    "Phone",
                    "Email",
                    "Department",
                    "Semester",
                    "Course Code",
                    "Course Name",
                    "CA",
                    "Exam",
                    "Total",
                    "Grade",
                    "Status",
                    "Present Days",
                    "Absent Days",
                    "Attendance %",
                ]
            )
            for student in self.students:
                writer.writerow(
                    [
                        student["id"],
                        student["name"],
                        student["gender"],
                        student["phone"],
                        student["email"],
                        student["department"],
                        student["semester"],
                        student["course_code"],
                        student["course_name"],
                        score_text(student["ca"]),
                        score_text(student["exam"]),
                        score_text(student["total"]),
                        student["grade"],
                        student["status"],
                        score_text(student["present_days"]),
                        score_text(student["absent_days"]),
                        score_text(student["attendance"]),
                    ]
                )
        self.write_report_status(f"CSV export generated:\n{filename}")
        messagebox.showinfo("CSV Exported", filename)

    def backup_database(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        copied = []
        for source, label in ((DATA_FILE, "students"), (COURSE_FILE, "courses")):
            if os.path.exists(source):
                destination = os.path.join(BACKUP_DIR, f"{label}_{self.timestamp()}.json")
                shutil.copy2(source, destination)
                copied.append(destination)
        if not copied:
            messagebox.showerror("Backup Failed", "No database files were found.")
            return
        self.write_report_status("Backup created:\n" + "\n".join(copied))
        messagebox.showinfo("Backup Created", "\n".join(copied))

    def show_student_ranking(self):
        ranking_window = tk.Toplevel(self)
        ranking_window.title("Student Ranking")
        ranking_window.geometry("1120x460")
        ranking_window.configure(bg=self.theme["bg"])

        tree = ttk.Treeview(
            ranking_window,
            columns=(
                "rank",
                "id",
                "name",
                "department",
                "semester",
                "course",
                "total",
                "grade",
                "status",
            ),
            show="headings",
        )
        for column, label, width in (
            ("rank", "Rank", 70),
            ("id", "ID", 130),
            ("name", "Name", 220),
            ("department", "Department", 110),
            ("semester", "Semester", 100),
            ("course", "Course", 240),
            ("total", "Total", 90),
            ("grade", "Grade", 80),
            ("status", "Status", 120),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=12)

        for rank, student in enumerate(self.ranked_students(), start=1):
            tree.insert(
                "",
                "end",
                values=(
                    rank,
                    student["id"],
                    student["name"],
                    student["department"],
                    student["semester"],
                    self.student_course_text(student),
                    score_text(student["total"]),
                    student["grade"],
                    student["status"],
                ),
            )

    def show_selected_profile(self):
        sid = self.selected_student_id
        if not sid:
            selection = self.student_tree.selection()
            sid = selection[0] if selection else ""
        student = self.find_student(sid)
        if not student:
            messagebox.showerror("Missing Student", "Select a student first.")
            return

        profile_window = tk.Toplevel(self)
        profile_window.title(f"Student Profile - {student['name']}")
        profile_window.geometry("620x520")
        profile_window.configure(bg=self.theme["bg"])

        details = tk.Text(profile_window, wrap="word", padx=18, pady=16)
        details.pack(fill="both", expand=True, padx=14, pady=14)
        details.configure(
            bg=self.theme["panel"],
            fg=self.theme["text"],
            insertbackground=self.theme["text"],
            highlightbackground=self.theme["border"],
            font=("Segoe UI", 11),
        )

        rows = (
            ("Student ID", student["id"]),
            ("Name", student["name"]),
            ("Gender", student["gender"]),
            ("Phone", student["phone"]),
            ("Email", student["email"]),
            ("Department", student["department"]),
            ("Semester", student["semester"]),
            ("Course", self.student_course_text(student)),
            ("CA Mark", score_text(student["ca"])),
            ("Exam Mark", score_text(student["exam"])),
            ("Total", score_text(student["total"])),
            ("Grade", student["grade"]),
            ("Status", student["status"]),
            ("Present Days", score_text(student["present_days"])),
            ("Absent Days", score_text(student["absent_days"])),
            ("Attendance %", score_text(student["attendance"])),
            ("Academic Alert", self.risk_reason(student) or "No risk detected"),
        )
        for label, value in rows:
            details.insert("end", f"{label}: {value}\n")
        details.configure(state="disabled")

    def show_at_risk_students(self):
        students = self.at_risk_students()
        if not students:
            messagebox.showinfo("At Risk Students", "No at-risk students found.")
            return

        risk_window = tk.Toplevel(self)
        risk_window.title("At Risk Students")
        risk_window.geometry("1120x460")
        risk_window.configure(bg=self.theme["bg"])

        tree = ttk.Treeview(
            risk_window,
            columns=(
                "id",
                "name",
                "department",
                "semester",
                "course",
                "total",
                "status",
                "attendance",
                "reason",
            ),
            show="headings",
        )
        for column, label, width in (
            ("id", "ID", 120),
            ("name", "Name", 190),
            ("department", "Department", 110),
            ("semester", "Semester", 100),
            ("course", "Course", 240),
            ("total", "Total", 80),
            ("status", "Status", 120),
            ("attendance", "Attendance %", 120),
            ("reason", "Reason", 220),
        ):
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=12)

        for student in students:
            tree.insert(
                "",
                "end",
                values=(
                    student["id"],
                    student["name"],
                    student["department"],
                    student["semester"],
                    self.student_course_text(student),
                    score_text(student["total"]),
                    student["status"],
                    score_text(student["attendance"]),
                    self.risk_reason(student),
                ),
            )

    def write_report_status(self, text):
        self.report_status.configure(state="normal")
        self.report_status.delete("1.0", "end")
        self.report_status.insert("1.0", text)
        self.report_status.configure(state="disabled")

    def draw_all_charts(self):
        if not hasattr(self, "grade_canvas"):
            return
        self.draw_grade_distribution()
        self.draw_pass_fail()
        self.draw_attendance()

    def draw_grade_distribution(self):
        grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for student in self.students:
            grades[student["grade"]] = grades.get(student["grade"], 0) + 1
        self.draw_bar_chart(self.grade_canvas, list(grades.items()), "Students")

    def draw_pass_fail(self):
        pass_count = len([student for student in self.students if student["status"] == "PASS"])
        fail_count = len([student for student in self.students if student["status"] == "FAIL"])
        distinction_count = len(
            [student for student in self.students if student["status"] == "DISTINCTION"]
        )
        self.draw_bar_chart(
            self.pass_canvas,
            [("Pass", pass_count), ("Fail", fail_count), ("Distinction", distinction_count)],
            "Count",
        )

    def draw_attendance(self):
        buckets = {"0-59": 0, "60-79": 0, "80-100": 0}
        for student in self.students:
            attendance = as_number(student.get("attendance", 0), 0)
            if attendance < 60:
                buckets["0-59"] += 1
            elif attendance < 80:
                buckets["60-79"] += 1
            else:
                buckets["80-100"] += 1
        self.draw_bar_chart(self.attendance_canvas, list(buckets.items()), "Students")

    def draw_bar_chart(self, canvas, data, axis_label):
        canvas.delete("all")
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 220)
        padding_left = 52
        padding_bottom = 42
        padding_top = 24
        padding_right = 24
        chart_width = width - padding_left - padding_right
        chart_height = height - padding_top - padding_bottom
        max_value = max([value for _label, value in data] + [1])

        canvas.configure(bg=self.theme["panel"])
        canvas.create_line(
            padding_left,
            padding_top,
            padding_left,
            height - padding_bottom,
            fill=self.theme["muted"],
        )
        canvas.create_line(
            padding_left,
            height - padding_bottom,
            width - padding_right,
            height - padding_bottom,
            fill=self.theme["muted"],
        )
        canvas.create_text(
            18,
            padding_top,
            text=axis_label,
            fill=self.theme["muted"],
            anchor="w",
            font=("Segoe UI", 9),
        )

        gap = 18
        bar_count = len(data)
        bar_width = max(28, (chart_width - gap * (bar_count + 1)) / max(bar_count, 1))
        for index, (label, value) in enumerate(data):
            x1 = padding_left + gap + index * (bar_width + gap)
            y1 = height - padding_bottom - (value / max_value * chart_height)
            x2 = x1 + bar_width
            y2 = height - padding_bottom
            color = self.theme["chart_colors"][index % len(self.theme["chart_colors"])]
            canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
            canvas.create_text(
                (x1 + x2) / 2,
                y1 - 10,
                text=str(value),
                fill=self.theme["text"],
                font=("Segoe UI", 10, "bold"),
            )
            canvas.create_text(
                (x1 + x2) / 2,
                height - padding_bottom + 18,
                text=label,
                fill=self.theme["text"],
                font=("Segoe UI", 10),
            )

    def apply_theme(self, mode):
        self.dark_mode = mode == "dark"
        self.theme = {
            "bg": "#101418" if self.dark_mode else "#f4f7f9",
            "panel": "#182027" if self.dark_mode else "#ffffff",
            "text": "#edf2f7" if self.dark_mode else "#202833",
            "muted": "#9ba8b4" if self.dark_mode else "#607080",
            "border": "#31404d" if self.dark_mode else "#d5dde5",
            "accent": "#0d8b73" if self.dark_mode else "#0f766e",
            "button": "#22303a" if self.dark_mode else "#e8eef3",
            "chart_colors": (
                "#0f766e",
                "#c2410c",
                "#2563eb",
                "#9333ea",
                "#ca8a04",
            ),
        }

        self.configure(bg=self.theme["bg"])
        self.header.configure(bg=self.theme["bg"])
        self.title_label.configure(bg=self.theme["bg"], fg=self.theme["text"])

        self.style.configure(".", background=self.theme["bg"], foreground=self.theme["text"])
        self.style.configure("TFrame", background=self.theme["bg"])
        self.style.configure("TLabelframe", background=self.theme["bg"])
        self.style.configure(
            "TLabelframe.Label", background=self.theme["bg"], foreground=self.theme["text"]
        )
        self.style.configure("TLabel", background=self.theme["bg"], foreground=self.theme["text"])
        self.style.configure(
            "TButton",
            background=self.theme["button"],
            foreground=self.theme["text"],
            padding=(10, 6),
        )
        self.style.map("TButton", background=[("active", self.theme["accent"])])
        self.style.configure(
            "TNotebook", background=self.theme["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0)
        )
        self.style.configure(
            "TNotebook.Tab",
            background=self.theme["button"],
            foreground=self.theme["text"],
            padding=(14, 8),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", self.theme["accent"])],
            foreground=[("selected", "#ffffff")],
        )
        self.style.configure(
            "Treeview",
            background=self.theme["panel"],
            fieldbackground=self.theme["panel"],
            foreground=self.theme["text"],
            rowheight=28,
            bordercolor=self.theme["border"],
        )
        self.style.configure(
            "Treeview.Heading",
            background=self.theme["button"],
            foreground=self.theme["text"],
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map("Treeview", background=[("selected", self.theme["accent"])])

        for card, title, value in self.dashboard_cards.values():
            card.configure(bg=self.theme["panel"], highlightbackground=self.theme["border"])
            title.configure(bg=self.theme["panel"], fg=self.theme["muted"])
            value.configure(bg=self.theme["panel"], fg=self.theme["text"])

        self.report_status.configure(
            bg=self.theme["panel"],
            fg=self.theme["text"],
            insertbackground=self.theme["text"],
            highlightbackground=self.theme["border"],
        )
        self.about_panel.configure(
            bg=self.theme["panel"], highlightbackground=self.theme["border"]
        )
        for index, label in enumerate(self.about_labels):
            label.configure(
                bg=self.theme["panel"],
                fg=self.theme["text"] if index in (0, 2, 3, 5) else self.theme["muted"],
            )
        self.draw_all_charts()

    def update_mark_preview(self):
        ca = as_number(self.student_ca_var.get(), None)
        exam = as_number(self.student_exam_var.get(), None)
        if ca is None or exam is None:
            self.student_total_var.set("0")
            self.student_grade_var.set("F")
            self.student_status_var.set("FAIL")
            return
        total = ca + exam
        self.student_total_var.set(score_text(total))
        self.student_grade_var.set(calculate_grade(total))
        self.student_status_var.set(calculate_status(total))

    def update_attendance_preview(self):
        present = as_number(self.student_present_var.get(), None)
        absent = as_number(self.student_absent_var.get(), None)
        if present is None or absent is None:
            self.student_attendance_var.set("0")
            return
        self.student_attendance_var.set(score_text(self.calculate_attendance(present, absent)))

    def calculate_attendance(self, present_days, absent_days, fallback=0):
        present = as_number(present_days, 0)
        absent = as_number(absent_days, 0)
        total_days = present + absent
        if total_days <= 0:
            return as_number(fallback, 0)
        return round((present / total_days) * 100, 1)

    def normalize_semester(self, semester_value):
        if semester_value is None:
            return ""
        semester_text = str(semester_value).strip()
        if not semester_text:
            return ""

        # Normalize numeric values and common semester strings
        digits = re.findall(r"\d+", semester_text)
        if digits:
            return f"Semester {int(digits[0])}"

        if semester_text.lower().startswith("semester"):
            parts = semester_text.split(None, 1)
            if len(parts) == 2 and parts[1].isdigit():
                return f"Semester {int(parts[1])}"
            return "Semester " + parts[1] if len(parts) == 2 else "Semester"

        return semester_text

    def course_options(self):
        return [f"{course['code']} - {course['name']}" for course in self.courses]

    def course_from_option(self, option):
        if " - " in option:
            code, name = option.split(" - ", 1)
            course = self.find_course(code.strip())
            if course:
                return course["code"], course["name"]
            return code.strip().upper(), name.strip()
        course = self.find_course(option.strip().upper())
        if course:
            return course["code"], course["name"]
        return option.strip().upper(), ""

    def student_course_text(self, student):
        code = student.get("course_code", "")
        name = student.get("course_name", "")
        if code and name:
            return f"{code} - {name}"
        return code or name

    def course_name_for_code(self, code):
        course = next(
            (item for item in getattr(self, "courses", []) if item["code"] == code), None
        )
        return course["name"] if course else ""

    def sync_student_course(self, old_code, course):
        for student in self.students:
            if student.get("course_code") == old_code:
                student["course_code"] = course["code"]
                student["course_name"] = course["name"]

    def handle_tab_change(self, _event):
        if self.notebook.select() == str(self.analytics_tab):
            self.after(50, self.draw_all_charts)

    def average_score(self):
        if not self.students:
            return 0
        return sum(as_number(student["total"]) for student in self.students) / len(
            self.students
        )

    def pass_rate(self):
        if not self.students:
            return 0
        passed = len([student for student in self.students if student["status"] != "FAIL"])
        return passed / len(self.students) * 100

    def ranked_students(self):
        return sorted(self.students, key=lambda student: as_number(student["total"]), reverse=True)

    def timestamp(self):
        return datetime.now().strftime("%Y%m%d_%H%M%S")


if __name__ == "__main__":
    login = LoginApp()
    login.mainloop()
    if login.authenticated:
        app = EduTrackApp()
        app.mainloop()
