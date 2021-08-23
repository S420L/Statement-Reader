import sqlite3

def dict_to_sqlite(box_dict, table_name, database):
	conn = sqlite3.connect(database)
	c = conn.cursor()
	c.execute("drop table if exists " + table_name + ";")
	sql_statement = "create table if not exists " + table_name + " ("
	box_dict_list = list(box_dict.keys())
	table_columns = ""
	for i in range(0,len(box_dict_list),1):
		if(i<len(box_dict_list)-1):
			sql_statement += str(box_dict_list[i]) + ' text,'
			table_columns += str(box_dict_list[i]) + ', '
		else:
			sql_statement += str(box_dict_list[i]) + ' text)'
			table_columns += str(box_dict_list[i])
	c.execute(sql_statement)
	for i in range(0,len(box_dict[list(box_dict.keys())[1]])):
		instruction_row = []
		for j in box_dict_list:
			instruction_row.append(box_dict[j][i])
		values = ['(']
		[values.append('''"'''+i+'''",''') for i in instruction_row]
		values.append(");") 
		values = "".join(values).replace(",)", ")")  # placeholder for values
		SQL = "INSERT INTO " + str(table_name) + "(" + str(table_columns) + ") values " + values
		#print(SQL)
		#print(instruction_row)
		c.execute(SQL)
		conn.commit()
	conn.close()

def run_SQL(SQL, commit_indic='n', database='C:\\Users\\micha\\Desktop\\Oasys code\\automation\\recipe_scraper\\OCR\\image_data.db'):
	conn = sqlite3.connect(database)
	c = conn.cursor()
	c.execute(SQL)
	data = c.fetchall()
	if(commit_indic=='y'):
		conn.commit()
		return
	c.close()
	conn.close()
	return data

def most_frequent(List):
    return max(set(List), key = List.count)