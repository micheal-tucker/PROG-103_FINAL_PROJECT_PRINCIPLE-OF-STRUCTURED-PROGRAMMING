
import csv
def export_csv(students,filename='reports/students.csv'):
    with open(filename,'w',newline='') as f:
        w=csv.writer(f)
        w.writerow(['ID','Name','Total','Grade'])
        for s in students:
            w.writerow([s['id'],s['name'],s['total'],s['grade']])
