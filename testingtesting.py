
def top_rule(data):
    top_thresh = 4
    passed = 0
    for i in range(0,len(data),3):
        top = int(data[i]['top'])
        if(i<len(data)-4):
            if((top + top_thresh)>int(data[i+1]['top']) and (top + top_thresh)>int(data[i+2]['top'])): #remove groups smaller than # columns
                 pass
            else:
                print("Removing...(group too small")
                print(data[i])
                print(data[i]['top'])
                print(data[i+1]['top'])
                passed = 1
                del data[i]
                return data, passed
            if(top<int(data[i+1]['top']) + top_thresh and top<int(data[i+2]['top']) + top_thresh and top<int(data[i+3]['top']) + top_thresh): #remove groups larger than # columns
                continue
            else:
                print("Removing... (group too large)")
                remove_list = []
                for j in range(0,len(data)):
                    if((int(data[j]['top'])<=top+top_thresh) and (int(data[j]['top'])>=top-top_thresh)):
                        remove_list.append(data[j])
                        print(data[j])
                data = [k for k in data if k['text'] not in [k['text'] for k in remove_list]]
                print("_________________________________")
                passed = 1
                return data, passed
        elif(i<len(data)-3):
            if((top + top_thresh)>int(data[i+1]['top']) and (top + top_thresh)>int(data[i+2]['top'])): #special case for removing groups from the end that are too small
                pass
            else:
                print("Removing...(group too small)")
                print(data[i])
                print("_________________________________")
                passed = 1
                del data[i]
                return data, passed
    return data, passed