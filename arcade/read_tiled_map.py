import xml.etree.ElementTree as etree
import base64
import zlib
import gzip

from arcade.isometric import isometric_grid_to_screen
from arcade import Sprite
from arcade import SpriteList


class TiledMap:

    def __init__(self):
        self.global_tile_set = {}
        self.layers_int_data = {}
        self.layers = {}
        self.version = None
        self.orientation = None
        self.renderorder = None
        self.width = None
        self.height = None
        self.tilewidth = None
        self.tileheight = None
        self.backgroundcolor = None
        self.nextobjectid = None


class Tile:

    def __init__(self):
        self.local_id = 0
        self.width = 0
        self.height = 0
        self.source = None
        self.points = None


class GridLocation:
    def __init__(self):
        self.tile = None
        self.center_x = 0
        self.center_y = 0


def _process_csv_encoding(data_text):
    layer_grid_ints = []
    lines = data_text.split("\n")
    for line in lines:
        line_list = line.split(",")
        while '' in line_list:
            line_list.remove('')
        line_list_int = [int(item) for item in line_list]
        layer_grid_ints.append(line_list_int)

    return layer_grid_ints


def _process_base64_encoding(data_text, compression, layer_width):
    layer_grid_ints = [[]]

    unencoded_data = base64.b64decode(data_text)
    if compression == "zlib":
        unzipped_data = zlib.decompress(unencoded_data)
    elif compression == "gzip":
        unzipped_data = gzip.decompress(unencoded_data)
    elif compression is None:
        unzipped_data = unencoded_data
    else:
        raise ValueError(f"Unsupported compression type '{compression}'.")

    # Turn bytes into 4-byte integers
    byte_count = 0
    int_count = 0
    int_value = 0
    row_count = 0
    for byte in unzipped_data:
        int_value += byte << (byte_count * 8)
        byte_count += 1
        if byte_count % 4 == 0:
            byte_count = 0
            int_count += 1
            layer_grid_ints[row_count].append(int_value)
            int_value = 0
            if int_count % layer_width == 0:
                row_count += 1
                layer_grid_ints.append([])

    layer_grid_ints.pop()
    return layer_grid_ints


def parse_points(point_text: str):
    result = []
    point_list = point_text.split(" ")
    for point in point_list:
        z = point.split(",")
        result.append([round(float(z[0])), round(float(z[1]))])

    return result


def read_tiled_map(filename: str, scaling) -> TiledMap:
    """
    Given a filename, this will read in a tiled map, and return
    a TiledMap object.
    """

    # Create a map object to store this stuff in
    my_map = TiledMap()

    # Read in and parse the file
    tree = etree.parse(filename)

    # Root node should be 'map'
    map_tag = tree.getroot()

    # Pull attributes that should be in the file for the map
    my_map.version = map_tag.attrib["version"]
    my_map.orientation = map_tag.attrib["orientation"]
    my_map.renderorder = map_tag.attrib["renderorder"]
    my_map.width = int(map_tag.attrib["width"])
    my_map.height = int(map_tag.attrib["height"])
    my_map.tilewidth = int(map_tag.attrib["tilewidth"])
    my_map.tileheight = int(map_tag.attrib["tileheight"])

    # Background color is optional, and may or may not be in there
    if "backgroundcolor" in map_tag.attrib:
        # Decode the background color string
        backgroundcolor_string = map_tag.attrib["backgroundcolor"]
        red_hex = "0x" + backgroundcolor_string[1:3]
        green_hex = "0x" + backgroundcolor_string[3:5]
        blue_hex = "0x" + backgroundcolor_string[5:7]
        red = int(red_hex, 16)
        green = int(green_hex, 16)
        blue = int(blue_hex, 16)
        my_map.backgroundcolor = (red, green, blue)

    my_map.nextobjectid = map_tag.attrib["nextobjectid"]

    # Grab all the tilesets
    tileset_tag_list = map_tag.findall('./tileset')

    # --- Tileset Data ---

    # Loop through each tileset
    for tileset_tag in tileset_tag_list:
        firstgid = int(tileset_tag.attrib["firstgid"])
        if "source" in tileset_tag.attrib:
            source = tileset_tag.attrib["source"]
            tileset_tree = etree.parse(source)

            # Root node should be 'map'
            tileset_root = tileset_tree.getroot()
            tile_tag_list = tileset_root.findall("tile")
        else:

            # Grab each tile
            tile_tag_list = tileset_tag.findall("tile")

        # Loop through each tile
        for tile_tag in tile_tag_list:

            # Make a tile object
            my_tile = Tile()
            image = tile_tag.find("image")
            my_tile.local_id = tile_tag.attrib["id"]
            my_tile.width = int(image.attrib["width"])
            my_tile.height = int(image.attrib["height"])
            my_tile.source = image.attrib["source"]
            key = str(firstgid)
            my_map.global_tile_set[key] = my_tile
            firstgid += 1

            objectgroup = tile_tag.find("objectgroup")
            if objectgroup:
                my_object = objectgroup.find("object")
                if my_object:
                    offset_x = round(float(my_object.attrib['x']))
                    offset_y = round(float(my_object.attrib['y']))
                    polygon = my_object.find("polygon")
                    if polygon is not None:
                        point_list = parse_points(polygon.attrib['points'])
                        for point in point_list:
                            point[0] += offset_x
                            point[1] += offset_y
                            point[1] = my_tile.height - point[1]
                            point[0] -= my_tile.width // 2
                            point[1] -= my_tile.height // 2
                            point[0] *= scaling
                            point[1] *= scaling
                            point[0] = int(point[0])
                            point[1] = int(point[1])

                        my_tile.points = point_list

    # --- Map Data ---

    # Grab each layer
    layer_tag_list = map_tag.findall('./layer')
    for layer_tag in layer_tag_list:
        layer_width = int(layer_tag.attrib['width'])

        # Unzip and unencode each layer
        data = layer_tag.find("data")
        data_text = data.text.strip()
        encoding = data.attrib['encoding']
        if 'compression' in data.attrib:
            compression = data.attrib['compression']
        else:
            compression = None

        if encoding == "csv":
            layer_grid_ints = _process_csv_encoding(data_text)
        elif encoding == "base64":
            layer_grid_ints = _process_base64_encoding(data_text, compression, layer_width)
        else:
            print(f"Error, unexpected encoding: {encoding}.")
            break

        # Great, we have a grid of ints. Save that according to the layer name
        my_map.layers_int_data[layer_tag.attrib["name"]] = layer_grid_ints

        # Now create grid objects for each tile
        layer_grid_objs = []
        for row_index, row in enumerate(layer_grid_ints):
            layer_grid_objs.append([])
            for column_index, column in enumerate(row):
                grid_location = GridLocation()
                if layer_grid_ints[row_index][column_index] != 0:
                    key = str(layer_grid_ints[row_index][column_index])
                    grid_location.tile = my_map.global_tile_set[key]

                    if my_map.renderorder == "right-down":
                        adjusted_row_index = my_map.height - row_index - 1
                    else:
                        adjusted_row_index = row_index

                    if my_map.orientation == "orthogonal":
                        grid_location.center_x = column_index * my_map.tilewidth + my_map.tilewidth // 2
                        grid_location.center_y = adjusted_row_index * my_map.tileheight + my_map.tilewidth // 2
                    else:
                        grid_location.center_x,  grid_location.center_y = isometric_grid_to_screen(column_index,
                                                                                                   row_index,
                                                                                                   my_map.width,
                                                                                                   my_map.height,
                                                                                                   my_map.tilewidth,
                                                                                                   my_map.tileheight)

                layer_grid_objs[row_index].append(grid_location)

        my_map.layers[layer_tag.attrib["name"]] = layer_grid_objs

    return my_map


def generate_sprites(map_object, layer_name, scaling, base_directory=""):
    sprite_list = SpriteList()

    if layer_name not in map_object.layers_int_data:
        print(f"Warning, no layer named '{layer_name}'.")
        return sprite_list

    map_array = map_object.layers_int_data[layer_name]

    # Loop through the layer and add in the wall list
    for row_index, row in enumerate(map_array):
        for column_index, item in enumerate(row):
            if str(item) in map_object.global_tile_set:
                tile_info = map_object.global_tile_set[str(item)]
                filename = base_directory + tile_info.source

                my_sprite = Sprite(filename, scaling)
                my_sprite.right = column_index * (map_object.tilewidth * scaling)
                my_sprite.top = (map_object.height - row_index) * (map_object.tileheight * scaling)

                if tile_info.points is not None:
                    my_sprite.set_points(tile_info.points)
                sprite_list.append(my_sprite)
            elif item != 0:
                print(f"Warning, could not find {item} image to load.")

    return sprite_list
