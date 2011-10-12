import csv
import json
import time
import urllib2
from geopy import geocoders
from geopy import distance  
from lxml.html import parse
from math import asin, cos, radians, sin, sqrt
#from operator import itemgetter

def haversine(lon2, lat2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    In this case, between any point and London - defined as 
    Soho Square (roughly equidistant from all stations, unlike
    Charing Cross, the traditional centre of London).
    Code adapted from http://stackoverflow.com/questions/4913349/
    """
    lat1 = 51.5151513
    lon1 = -0.1327293
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a)) 
    km = 6367 * c
    return km
    
def get_missing_distances(infile, outfile):
    reader = csv.reader(open(infile,"rbU"))
    writer = csv.writer(open(outfile,"wb"))
    for i, row in enumerate(reader):
        if i==0: 
            writer.writerow(row)  
            continue
        lat = row[29].strip()
        lng = row[30].strip()
        distance = row[31].strip()
        if lat and lng and (distance.strip() == ''):
            row[31] = haversine(float(lng), float(lat))
        writer.writerow(row)
       
def get_latlngs(infile, outfile):
    ''' 
    Get the lat/lng of each station using Google's geocoder. 
    Try postcode first, then station name if that fails. 
    Add Haversine distance from London once lat/lngs are found. 
    A few stations need to be corrected by hand afterwards,
    because Google's geocoder puts them elsewhere in the world: 
    Kiveton Bridge: 53.34098, -1.26718
    Kiveton Park: 53.33674, -1.23985
    Bentham: 54.1158, -2.51091
    Ribblehead: 54.20585, -2.36085
    Penistone: 53.52557, -1.62278
    Walton-On-Naze: 51.84618, 1.26769
    Annan: 54.98384, -3.26258
    Radyr: 51.51633, -3.24836 
    Llandaf: 51.50844, -3.22862
    '''
    reader = csv.reader(open(infile,"rb"))
    writer = csv.writer(open(outfile,"wb"))
    g = geocoders.Google(domain='maps.google.co.uk') 
    london_geocoded = g.geocode("london", exactly_one=False)
    for i, row in enumerate(reader):
        if i==0: 
            row.append('WGS84 Lat')
            row.append('WGS84 Lng')
            row.append('Distance from London (km)')
            writer.writerow(row)  
            continue
        time.sleep(1)
        postcode = row[8].strip()
        if postcode:
            station_name = row[2].strip() + " Rail Station, UK"
            if i % 100 == 0:
                print i, station_name
            try:
                georesults = g.geocode(postcode, exactly_one=False)
            except geocoders.google.GQueryError: 
                try: 
                    georesults = g.geocode(station_name, exactly_one=False)        
                except geocoders.google.GQueryError: 
                    georesults = [(None, (None, None))]
            place, (lat, lng) =  georesults[0] 
            # Check lat and lng are within the rough boundaries of the UK. 
            # Some of the Guardian's postcodes are dubious!
            if 49.0 > lat or 59.0 < lat or -8.0 > lng or 2.0 < lng:
                print "OUTSIDE BOUNDARIES OUTSIDE UK: %s, %s, %s" % (station_name, lat, lng)
            distance = haversine(float(lng), float(lat))
            writer.writerow(row+[lat]+[lng]+[distance])  
            
def find_id(data_list, name):
    for i,d in enumerate(data_list):
        if d['metadata_name'] == name:
            return i
    return -1
    
def get_average_price(data):
    '''
    Get the average price over the last six months, from Nestoria.
    If there are four or more months with fewer than 2 listings, bin the data.
    '''
    avg = 0.0
    slow_months = 0
    for k,v in data.items():
        avg += float(v['avg_price'])
        if int(v['datapoints']) < 2:
            slow_months += 1
    avg = avg / len(data.items())   
    if slow_months < 4:        
        return avg
    else:
        return None
     
def get_nestoria_prices(infile, outfile):
    ''' 
    Get average sale prices from the Nestoria API.
    '''
    reader = csv.reader(open(infile,"rbU"))
    writer = csv.writer(open(outfile,"wb"))
    for i, row in enumerate(reader):
        if i==0: 
            row.append('Nestoria Avg 2-Bed House')
            row.append('Nestoria Avg 3-Bed House')
            row.append('Avg Time to London')
            row.append('Notes')
            writer.writerow(row)
            continue
        lat = row[29].strip()
        lng = row[30].strip()
        station_name = row[2].strip() 
        print i, station_name
        if lat and lng:
            nestoria_url = 'http://api.nestoria.co.uk/api?country=uk&pretty=1&action=metadata&centre_point=%s,%s&encoding=json' % (lat, lng)
            print nestoria_url
            req = urllib2.Request(nestoria_url)
            opener = urllib2.build_opener()
            f = opener.open(req)
            nest = json.load(f)
            try: 
                results = nest['response']['metadata']
                avg_price_2_bed = None
                avg_price_3_bed = None
                bed_2_id = find_id(results,'avg_2bed_property_buy_monthly')
                bed_3_id = find_id(results,'avg_3bed_property_buy_monthly')
                if bed_2_id!=-1:
                    avg_price_2_bed = get_average_price(results[bed_2_id]['data'])
                if bed_3_id!=-1:
                    avg_price_3_bed = get_average_price(results[bed_3_id]['data'])
                print avg_price_2_bed, avg_price_3_bed
                note = ''
                if not avg_price_3_bed or (avg_price_3_bed == 0):
                    note = "Not enough Nestoria data for 3-bed price"
                    avg_price_3_bed = None # Don't write zeroes to the data.
                writer.writerow(row+[avg_price_2_bed]+[avg_price_3_bed]+['']+[note])
            except KeyError:
                # No suitable response from Nestoria.
                writer.writerow(row+['']+['']+['']+[''])
    

def get_traintimes_info(infile, outfile):
    ''' 
    Calcuate average travel times and prices, using Traintimes. 
    Calcuations are based on the five journeys to London, departing at
    8am the next day.
    Some stations fail - those that are already in London, or those 
    that are dead station codes, or Parliamentary services.
    Also, Farringdon has a dodgy postcode, so delete that. 
    '''
    reader = csv.reader(open(infile,"rbU"))
    writer = csv.writer(open(outfile,"wb"))
    BASE_URL = 'http://traintimes.org.uk'
    for i, row in enumerate(reader):
        if i==0: 
            writer.writerow(row)
            continue
        if len(row) < 36:
            row += [''] * (36 - len(row))
        station = row[1].strip()
        if station:
            print i, row[2].strip()
            # Scrape journeys leaving 8am on Wednesday, prefer direct 
            traintimes = BASE_URL + ('/%s/london/08:00/wednesday/' % station)
            print traintimes
            doc = parse(traintimes).getroot()
            clean_results = []
            for li in doc.cssselect('ul.results li'):
                cleantext = ' '.join((li.text_content()).split())
                clean_results.append(cleantext)
            if clean_results:
                journey_times = []
                for journey in clean_results:
                    x = journey.split('(')
                    y = x[1].split(',')
                    travel_time = y[0]
                    test_time = travel_time.split("h")
                    if len(test_time)>1:
                        hours = int(test_time[0])
                        minutes = int(test_time[1].replace("m",''))
                    else:
                        hours = 0
                        minutes = int(test_time[0].replace("m",''))
                    total_minutes = hours*60 + minutes
                    journey_times.append(total_minutes)
                # We now have the 5 journey times - calculate the average. 
                print journey_times
                avg_jt = float(sum(journey_times))/len(journey_times)
                print avg_jt
                row[34] = avg_jt
                # TODO: get the price of the first journey (cheapest price, whatever it is).
                #fares_link = doc.cssselect('a.fares_link')
                #prices_link = fares_link[0].get('href')
                #print prices_link
                #doc = parse(BASE_URL + prices_link).getroot()
                #cheapest_fare = doc.cssselect('a.fares_link')                                                                                                                                                                                                                                                                                                                                                                                  
                #all_results.append(row)\
                writer.writerow(row)
                time.sleep(0.6)
            else:
                print 'no results found - station may be in London, or out of use'
                time.sleep(0.6)
                row[34] = ''
                row[35] = 'No Traintimes results found - station out of use?'
                writer.writerow(row)

MOVING_AVERAGE_SIZE = 100
TOTAL_ROWS = 2525

def get_average_frame(i):
    lower = i - (MOVING_AVERAGE_SIZE / 2)
    upper = i + (MOVING_AVERAGE_SIZE / 2)
    if lower < 1: lower = 1
    if upper > (TOTAL_ROWS): upper = TOTAL_ROWS
    return lower, upper
    
def get_moving_averages(infile, outfile, avg_type):
    ''' 
    Calculates moving averages. 
    IMPORTANT: re-sort by the factor that you want to average by
    (time to London, or distance) before running.
    '''
    reader = csv.reader(open(infile,"rbU"))
    writer = csv.writer(open(outfile,"wb"))
    BASE_URL = 'http://traintimes.org.uk'
    mylist = list(reader)
    for i, row in enumerate(mylist):
        if i==0: 
            row.append('Moving Average')
            writer.writerow(row)
            continue
        if len(row) < 37:
            row += [''] * (37 - len(row))
        lower, upper = get_average_frame(i)
        total = 0
        num_rows = 0
        for j in range(lower,upper): 
            if mylist[j][33] and float(mylist[j][33]) != 0.0: 
                num_rows += 1
                total += float(mylist[j][33])
        moving_average_price = total / num_rows
        row[36] = moving_average_price
        writer.writerow(row)
                                
#get_latlngs("allstations_sorted_by_visitors.csv", "stations_out.csv")
#get_nestoria_prices("stations_out.csv", "stations_out_nestoria.csv")
#get_traintimes_info("stations_out_nestoria.csv","stations_out_traintimes.csv")
get_moving_averages("stations_out_traintimes.csv","stations_out_averages.csv")