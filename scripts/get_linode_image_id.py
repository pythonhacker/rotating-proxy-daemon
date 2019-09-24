import json

def query_linode_image_id():
    """ Query for linode image id and write to proxy.conf """

    image_id = raw_input('Enter linode image id: ')
    try:
        im_id = int(image_id)
        cfg = json.load(open('proxy.conf'))
        cfg['image_id'] = im_id
        json.dump(cfg, open('proxy.conf','w'), indent=4)
    except ValueError, e:
        print 'Invalid image id=>',image_id
    except Exception, e:
        print 'Error updating proxy.conf =>',e
        
if __name__ == "__main__":
    query_linode_image_id()
