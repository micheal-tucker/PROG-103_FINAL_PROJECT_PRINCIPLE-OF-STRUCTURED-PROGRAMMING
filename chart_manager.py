
import matplotlib.pyplot as plt

def show_grade_chart(students):
    grades={'A':0,'B':0,'C':0,'D':0,'F':0}
    for s in students:
        grades[s['grade']]+=1
    plt.bar(grades.keys(),grades.values())
    plt.title('Grade Distribution')
    plt.show()
