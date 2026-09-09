from pathlib import Path

path = Path("test.txt")

list1 = [("a", "1"), ("b", "2"), ("c", "3")]
list2 = [0, 2]

selection_names = (str(list1[i][0]) + "\n" for i in list2)

with open(path, "w") as f:
    f.writelines(selection_names)
