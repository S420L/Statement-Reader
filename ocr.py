import os
import time
import tempfile
import pandas as pd
from tkinter import Tk
from pytesseract import Output
from pdf2image import convert_from_path
from tkinter.filedialog import askopenfilename
from pytesseract import image_to_data as Tessa_image_to_data
from cv2 import imread, imwrite, cvtColor, COLOR_BGR2GRAY, rectangle, imshow, waitKey
from tricks import dict_to_sqlite, run_SQL, most_frequent, send_to_excel, list_to_dict

pd.options.mode.chained_assignment = None  # default='warn'

def show_rectangles(image_data):
	'''function for showing borders around words (visualize the data from image_to_data)
	'''
	for i in range(0,len(image_data['line_num'])):
		(x, y, w, h) = (image_data['left'][i], image_data['top'][i], image_data['width'][i], image_data['height'][i])
	rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
	imshow('Results',image)
	waitKey(0)
	return

#get text from image
def image_to_text(filename):
	image = imread(filename)
	gray = cvtColor(image, COLOR_BGR2GRAY)
	filename = str(os.path.abspath(os.path.dirname(__file__))+"{}.png").format(os.getpid())
	imwrite(filename, gray)
	image_data = Tessa_image_to_data(filename, output_type = Output.DICT)
	os.remove(filename)
	return image_data

#get image from PDF
def pdf_to_image(filename):
	with tempfile.TemporaryDirectory() as path:
		images_from_path = convert_from_path(filename, output_folder=os.path.abspath(os.path.dirname(__file__)))
		print('running for image: ' + str(images_from_path))
		filenames = [i.filename for i in images_from_path]
		return filenames

def group_by_lines(image_lines):
	'''
	 --  do the iterative migration top to bottom, if an element is too close to the top of the page to be in its index then move down by one
	 -- "passed" indicates weather or not the algorithm has yet converged
	'''
	passed = 0
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			first_top = image_lines[i][0]['top']
			if((image_lines[i][j]['top']+5<first_top)):
					if(image_lines[i][j]['line_num']>0):
						image_lines[i][j]['line_num'] -= 1
						passed = 1
					else:
						image_lines[i][j]['text'] = "" #terminate journey of this number, its probably from the top of the sheet
	return image_lines, passed

def fix_image_lines(image_lines):
	'''part 2 of algorithm, fix reweighted list items so they're grouped right
	'''
	max_line_num = max([i['line_num'] for i in image_lines[-1]])
	temp_list = [[] for i in range(0,max_line_num+1)]
	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			temp_list[image_lines[i][j]['line_num']].append(image_lines[i][j])
	return_list = []
	for i in range(0,len(temp_list)):
		first_half = [] #anchor the first word to ensure lines are constant
		second_half = []
		for j in [k for k in temp_list[i] if len(k)>0]:
			if(j['text'].replace(",","").replace("$","").replace("(","").replace(")","").replace(" ","").replace("-","").replace("0.","").strip().lower().isdigit()):
				second_half.append(j)
			else:
				first_half.append(j)
		return_list.append(first_half+second_half)
	return return_list

def get_color(image_data, d):
	'''get most likely color of text (sampled through the midline of the rectangle surrounding the word)
	'''
	return_dict = {'level':[],'left':[],'top':[],'width':[],'height':[],'text':[],'R':[], 'G':[], 'B':[],'count':[],'percent':[]} 
	for w in range(0,len(d['left']),1):
		pixel_list = []
		for i in range(d['left'][w],d['left'][w]+d['width'][w],1):
			pixel_list.append(image_data[d['top'][w]+(int(d['height'][w]/2))][i]) #sample pixels in a line through the middle of each box
		pixel_list = [i for i in pixel_list if int(i[0]) + int(i[1]) + int(i[2]) < 742] #disregard anything that's basically white
		pixel_list = [[int(i[0]),int(i[1]),int(i[2])] for i in pixel_list]
		if(len(pixel_list)>0 and d['text'][w]!=''): #only run for boxes with words in them
			df = pd.DataFrame.from_records(pixel_list) #turn dict into dataframe
			df.columns = ['B','G','R'] #this library reverses the rgb order
			df = df.groupby(['B','G','R']).size().reset_index().rename(columns={0:'count'}) #on the equator of the box, we want to see how many of each (non-white) color show up 
			df['percent'] = df['count']/df['count'].sum() #get % of pixels on the center line that are that color
			final_row = df[df['count']==df['count'].max()]
			#print(final_row)
			#print("text ^^: " + str(d['text'][w]))
			if(len(final_row['count'])>1): #force it to be distinct
				final_row['R'] = int(final_row['R'].sum()/len(final_row)) #avg the colors
				final_row['G'] = int(final_row['G'].sum()/len(final_row)) 
				final_row['B'] = int(final_row['B'].sum()/len(final_row))
				final_row['count'] = int(final_row['count'].max()) #take the max count
				final_row['percent'] = float(final_row['percent'].max())
				final_row = final_row.drop_duplicates()
			final_row = final_row.to_dict('series')
			return_dict['level'].append(str(d['level'][w]))  #add variables that didn't change
			return_dict['left'].append(str(d['left'][w]))
			return_dict['top'].append(str(d['top'][w]))
			return_dict['width'].append(str(d['width'][w]))
			return_dict['height'].append(str(d['height'][w]))
			return_dict['text'].append(str(d['text'][w]))
			return_dict['R'].append(str(final_row['R'].values[0]))  #add variables that were generated in this function
			return_dict['G'].append(str(final_row['G'].values[0]))
			return_dict['B'].append(str(final_row['B'].values[0]))
			return_dict['count'].append(str(final_row['count'].values[0]))
			return_dict['percent'].append(str(final_row['percent'].values[0]))
	return return_dict

#gui
Tk().withdraw()
filename = askopenfilename()
#filename = os.path.abspath(os.path.dirname( __file__ ))+'dd70d073-44fe-4814-a9f2-adcc2c7fa3f3-2.ppm' #manual for testing

"""image_data = cv2.imread(filename,1) #get color of whatever we're looking at
img = cv2.imread(filename)
d = Tessa.image_to_data(img, output_type = Output.DICT)
print('LEN D: ' + str(len(d['left']))) #how long is the dict we're putting into function?
box_dict = get_color(image_data,d) #get RGB info on characters
print('LEN box_dict:: '+ str(len(box_dict['R']))) #how long is the dict we're getting out?
print(box_dict.keys())

dict_to_sqlite(box_dict,'image_table', 'image_data.db')"""

#if it's a PDF, convert to image first
start_time = time.time()
try:
	images = pdf_to_image(filename)
	print("PDF")
except:
	images = [filename]
	print("image")

full_image_data = []
for image in images:
	image_data = image_to_text(image)
	full_image_data.append(image_data) #only use image data (includes text)

SQL = """delete from financials;"""
run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
for image_data in full_image_data:
	temp_data = {'text': [], 'top': [], 'left': [], 'line_num': []}
	for i in range(0,len(image_data['text'])):
		if(image_data['text'][i]!=""):
			temp_data['text'].append(image_data['text'][i])
			temp_data['top'].append(image_data['top'][i])
			temp_data['left'].append(image_data['left'][i])
			temp_data['line_num'].append(image_data['line_num'][i])
	image_data = temp_data
	image_lines = [[{key: image_data[key][0] for key in ('text','top','left')}]]
	image_lines[0][0]['line_num'] = 0
	tack_on = []
	line_num = 1 
	for i in range(0,len(image_data['text'])):
		if image_data['left'][i]<100:
			if(image_data['top'][i]>image_lines[len(image_lines)-1][0]['top']+5):
				line = {key: image_data[key][i] for key in ('text','top','left','line_num')}
				line['line_num'] = line_num
				line_num+=1
				image_lines.append([line])
			else:
				tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})
		else:
			tack_on.append({key: image_data[key][i] for key in ('text','top','left','line_num')})

	tack_on = sorted(tack_on, key = lambda num: num['top'], reverse=True)
	for i in tack_on:
		image_lines[-1].append(i)
	max_line_num = len(image_lines)-1
	
	for i in range(0,len(image_lines[-1])):
		image_lines[-1][i]['line_num'] = max_line_num

	for i in range(0,len(image_lines)):
		image_lines[i] = [k for k in image_lines[i] if k['text'].strip()!=""]

	for i in range(0,len(image_lines)):
		for j in range(0,len(image_lines[i])):
			if(image_lines[i][j]['text'].strip()==b'\xe2\x80\x94'.decode('utf-8')):
				image_lines[i][j]['text'] = str(0)
				image_lines[i][j]['top'] = float(image_lines[i][j]['top']) - 10
			elif(image_lines[i][j]['text'].strip()[0]=="(" and image_lines[i][j]['text'][-1].strip()==")"):
				if(image_lines[i][j]['text'].replace("(","").replace(")","").replace("0.","").replace(".","").strip().isdigit()):
					image_lines[i][j]['text'] = str("—" + image_lines[i][j]['text'][1:-1])

	original_image_lines = [i for i in image_lines]

	#for i in image_lines:
	#	print(i[0]['text'])
	#	print(i[0]['line_num'])
	#for i in image_lines:
	#	print(min([j['line_num'] for j in i]))
	#for i in image_lines:
	#	print(len(i))
	#for i in image_lines:
	#	if(len(i)>0):
	#		print(i[0]['text'])

	for i in range(0,100):	
		image_lines, passed = group_by_lines(image_lines)
		image_lines = fix_image_lines(image_lines)

	# sort lines left to right
	for i in range(0,len(image_lines)):
		image_lines[i] = sorted(image_lines[i], key = lambda var: var['left'], reverse = False)

	for i in range(0,len(image_lines)):
		for j in range(1,len(image_lines[i])):
			if(image_lines[i][j]['text']==image_lines[i][j-1]['text'] and image_lines[i][j]['top']==image_lines[i][j-1]['top']):
				image_lines[i][j]['text'] = ""

	print("Passed? " + str(passed))
	print("___________________________________")
	print([i for i in image_lines[0]])
	print("___________________________________")
	print([i['text'] for i in image_lines[1]])
	print("___________________________________")
	print([i['text'] for i in image_lines[7]])

	for i in range(0,len(image_lines)):
		image_lines[i] = {'text': [k['text'].replace("$","").replace(",","").strip().lower() for k in image_lines[i] if len(k['text'].replace("$","").strip().lower())>0]}
	company_name = "UNKNOWN"
	for i in image_lines:
		for j in range(0,len(i['text'])):
			if 'inc.' in i['text'][j] or 'llc.' in i['text'][j]:
				try:
					company_name = i['text'][j-1]
				except:
					company_name = 'INC AT START OF LINE'
	
	for i in range(0,len(image_lines)):
		values = []
		variable = ""
		for j in image_lines[i]['text']:
			if(j.replace(b'\xe2\x80\x94'.decode('utf-8'),"").replace("0.","").replace(".","").replace("-","").strip().isdigit()):
				values.append(j)
			else:
				variable += " " + str(j)
		image_lines[i]['variable'] = variable.replace("\"","")
		image_lines[i]['values'] = values
		
	data_dict = {'rank': [],'variable': [], 'year': [], 'value': []}
	num_years = most_frequent([len(i['values']) for i in image_lines])

	for i in range(0,len(image_lines)):
		if(len(image_lines[i]['values'])==num_years and image_lines[i]['variable']!=""):
			for j in range(0,num_years):
				data_dict['rank'].append(str(i))
				data_dict['variable'].append(image_lines[i]['variable'].strip().lower())
				data_dict['year'].append(str(2020-j))
				data_dict['value'].append(image_lines[i]['values'][j])
		elif(len(image_lines[i]['values'])==0 and image_lines[i]['variable']!=""):
			data_dict['rank'].append(str(i))
			data_dict['variable'].append(image_lines[i]['variable'].strip().lower())
			data_dict['year'].append("HEADING")
			data_dict['value'].append("HEADING")

	print("_____Inputting first half______")
	[print(len(data_dict[i])) for i in data_dict.keys()]
	dict_to_sqlite(data_dict, "financials_temp_1", str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
	SQL = """
	insert into financials
	select * from financials_temp_1;
	"""
	run_SQL(SQL, commit_indic='y', database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))

SQL = """
	select * from (
	select distinct rank, variable, sum(case
	when year=2020 then value end) as this_year, sum(case 
	when year=2019 then value end) as last_year, sum(case
	when year=2019 then value end) as year_before, count(*) as total
	from financials
	group by rank, variable
	order by cast(rank as 'decimal'))
	where total<=3;
	"""
data = run_SQL(SQL, database=str(os.path.abspath(os.path.dirname(__file__))+"/image_data.db"))
data = [{'variable': i[1], '2020': i[2], '2019': i[3], '2018': i[4]} for i in data]
data = list_to_dict(data)

send_to_excel(os.path.dirname(__file__),data,"Financial Statement Output",clear_indic='n')
print("finished running in: " + str(time.time()-start_time) + " seconds")

