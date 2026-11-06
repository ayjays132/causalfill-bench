"""Independent pixel identities, calibration invariants, and malformed-image controls."""
import base64
import binascii
from copy import deepcopy
import hashlib
import math
import struct
import unittest
import zlib

from causalfill.vision import (
    ENVELOPE_KEYS, PNG_SIGNATURE, decode_envelope, decode_png, detect_components,
    encode_png, image_envelope, pixel_to_world, recover_calibration, render_scene,
    world_to_pixel,
)


def chunk(kind, payload):
    # Deliberately independent writer for malformed and alternate encodings.
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',binascii.crc32(kind+payload)&0xffffffff)


def png_payload(width,height,raw,extra=b'',color=2,depth=8):
    header=struct.pack('>IIBBBBB',width,height,depth,color,0,0,0)
    return PNG_SIGNATURE+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(raw)+extra)+chunk(b'IEND',b'')


class PixelFormatTests(unittest.TestCase):
    def test_rgb_roundtrip_has_only_permitted_chunks(self):
        rgb=bytes([0,1,2,250,251,252,90,80,70,7,8,9,22,23,24,40,50,60])
        png=encode_png(3,2,rgb)
        self.assertEqual(decode_png(png),(3,2,rgb))
        self.assertEqual(png[12:16],b'IHDR')
        pos=8
        kinds=[]
        while pos < len(png):
            n=struct.unpack('>I',png[pos:pos+4])[0]
            kinds.append(png[pos+4:pos+8]); pos+=12+n
        self.assertEqual(kinds,[b'IHDR',b'IDAT',b'IEND'])
        envelope=image_envelope(png)
        self.assertEqual(set(envelope),set(ENVELOPE_KEYS))
        self.assertEqual(decode_envelope(envelope),(3,2,rgb))

    def test_external_standard_zlib_multiple_idat_is_accepted(self):
        raw=b'\0'+bytes([1,2,3])*4
        comp=zlib.compress(raw)
        header=struct.pack('>IIBBBBB',4,1,8,2,0,0,0)
        encoded=PNG_SIGNATURE+chunk(b'IHDR',header)+chunk(b'IDAT',comp[:4])+chunk(b'IDAT',comp[4:])+chunk(b'IEND',b'')
        self.assertEqual(decode_png(encoded),(4,1,bytes([1,2,3])*4))

    def test_decompression_overflow_and_concatenated_streams_rejected(self):
        cases=[png_payload(1,1,b'\0'*100_000),
               png_payload(1,1,b'\0\1\2\3',extra=zlib.compress(b'secret')),
               png_payload(1,1,b'\0\1\2\3',extra=b'extra'),
               png_payload(2,1,b'\0\1\2\3')]
        for value in cases:
            with self.subTest(length=len(value)),self.assertRaises(ValueError):decode_png(value)

    def test_metadata_crc_truncation_trailing_bytes_and_profile_rejected(self):
        valid=encode_png(1,1,b'\x00\x80\xff')
        bad_crc=bytearray(valid);bad_crc[32]^=1
        metadata=valid[:-12]+chunk(b'tEXt',b'answer=WEST')+valid[-12:]
        invalid=[valid+b'\x00',valid[:-1],bytes(bad_crc),metadata,
                 png_payload(1,1,b'\0\0\0\0',color=6),
                 png_payload(1,1,b'\1\0\0\0'),
                 png_payload(1025,1,b'\0\0\0\0')]
        for value in invalid:
            with self.subTest(length=len(value)),self.assertRaises(ValueError):decode_png(value)

    def test_dimension_and_envelope_types_reject_boolean_and_tampering(self):
        for args in [(True,1,b'aaa'),(1,0,b''),(1,1,b'aa'),(1,1,bytearray(b'aaa'))]:
            with self.assertRaises(ValueError): encode_png(*args)
        image=image_envelope(encode_png(1,1,b'abc'))
        variants=[]
        for key,value in [('width',True),('height',2),('sha256','f'*64),('png_base64','!'),('hidden',7)]:
            candidate=deepcopy(image);candidate[key]=value;variants.append(candidate)
        for value in variants:
            with self.assertRaises(ValueError):decode_envelope(value)


class RasterGeometryTests(unittest.TestCase):
    def test_inverse_pixel_sampling_matches_independent_rectangle_mask(self):
        image=render_scene([{'shape':'rect','bounds':[2,3,5,6],'rgb':[200,50,80]}],
                           {'width':16,'height':16,'matrix':[[2,0,1],[0,2,0]]},background=(0,0,0))
        w,h,rgb=decode_envelope(image)
        for y in range(h):
            for x in range(w):
                expected=bytes((200,50,80)) if 5<=x<11 and 6<=y<12 else b'\0\0\0'
                self.assertEqual(rgb[3*(y*w+x):3*(y*w+x)+3],expected)

    def test_noise_bound_is_independent_of_geometry_and_occluded_twins(self):
        camera={'width':48,'height':40,'matrix':[[1,0,0],[0,1,0]]}
        full={'shape':'rect','bounds':[0,0,48,40],'rgb':[120,130,140]}
        image=render_scene([full],camera,noise=6,noise_seed=147)
        w,h,raw=decode_envelope(image)
        self.assertTrue(all(abs(value-[120,130,140][i%3])<=6 for i,value in enumerate(raw)))
        self.assertEqual(image,render_scene([full],camera,noise=6,noise_seed=147))
        self.assertNotEqual(image['sha256'],render_scene([full],camera,noise=6,noise_seed=148)['sha256'])
        first={'shape':'circle','center':[6,8],'radius':4,'rgb':[221,66,145]}
        second={'shape':'circle','center':[31,22],'radius':4,'rgb':[221,66,145]}
        self.assertEqual(render_scene([first,full],camera,noise=6,noise_seed=9),
                         render_scene([second,full],camera,noise=6,noise_seed=9))

    def test_visible_partial_and_offscreen_components_are_not_hallucinated(self):
        camera={'width':32,'height':24,'matrix':[[1,0,0],[0,1,0]]}
        shapes=[{'shape':'rect','bounds':[-5,3,7,9],'rgb':[200,40,50]},
                {'shape':'rect','bounds':[10,3,16,9],'rgb':[200,40,50]},
                {'shape':'rect','bounds':[40,3,48,9],'rgb':[200,40,50]}]
        image=render_scene(shapes,camera)
        components=detect_components(image,[200,40,50],tolerance=0)
        self.assertEqual([x['area'] for x in components],[42,36])
        self.assertEqual(components[0]['bbox'],[0,3,6,8])
        self.assertEqual(components[0]['center'],[3.5,6.0])

    def test_reflections_rotations_shear_and_calibration_from_pixels(self):
        landmarks=[{'world':[5,5],'rgb':[220,40,60]},
                   {'world':[35,5],'rgb':[40,190,80]},
                   {'world':[5,35],'rgb':[60,80,220]}]
        orientations=[[[1,0],[0,1]],[[0,-1],[1,0]],[[-1,0],[0,-1]],[[0,1],[-1,0]],
                      [[-1,0],[0,1]],[[1,0],[0,-1]],[[0,1],[1,0]],[[0,-1],[-1,0]]]
        shapes=[{'shape':'circle','center':l['world'],'radius':2,'rgb':l['rgb']} for l in landmarks]
        shapes.append({'shape':'circle','center':[15,25],'radius':2.5,'rgb':[220,180,50]})
        for orient in orientations:
            linear=[[orient[i][0]*2,orient[i][0]*0.4+orient[i][1]*2] for i in range(2)]
            matrix=[[row[0],row[1],60-20*sum(row)] for row in linear]
            image=render_scene(shapes,{'width':120,'height':120,'matrix':matrix},noise=6,noise_seed=0)
            recovered=recover_calibration(image,landmarks,tolerance=6)
            comp=detect_components(image,[220,180,50],tolerance=6)[0]
            point=pixel_to_world(recovered,comp['center'])
            self.assertAlmostEqual(point[0],15,places=6)
            self.assertAlmostEqual(point[1],25,places=6)
            for actual,expected in zip(sum(recovered,[]),sum(matrix,[])):
                self.assertAlmostEqual(actual,expected,places=6)

    def test_missing_ambiguous_and_collinear_fiducials_fail_closed(self):
        landmarks=[{'world':[5,5],'rgb':[220,40,60]},
                   {'world':[25,5],'rgb':[40,190,80]},
                   {'world':[5,25],'rgb':[60,80,220]}]
        shapes=[{'shape':'circle','center':l['world'],'radius':2,'rgb':l['rgb']} for l in landmarks]
        camera={'width':40,'height':40,'matrix':[[1,0,0],[0,1,0]]}
        for bad in [shapes[:2],shapes+[{'shape':'circle','center':[30,30],'radius':2,'rgb':landmarks[0]['rgb']}]]:
            with self.assertRaises(ValueError):recover_calibration(render_scene(bad,camera),landmarks)
        collinear=deepcopy(landmarks);collinear[2]['world']=[45,5]
        with self.assertRaises(ValueError):recover_calibration(render_scene(shapes,camera),collinear)

    def test_camera_and_primitive_validation_rejects_nonfinite_bool_unknown(self):
        camera={'width':32,'height':32,'matrix':[[1,0,0],[0,1,0]]}
        invalid=[{'shape':'circle','center':[True,2],'radius':2,'rgb':[1,2,3]},
                 {'shape':'circle','center':[10**1000,2],'radius':2,'rgb':[1,2,3]},
                 {'shape':'rect','bounds':[2,2,1,3],'rgb':[1,2,3]},
                 {'shape':'circle','center':[2,2],'radius':math.inf,'rgb':[1,2,3]},
                 {'shape':'circle','center':[2,2],'radius':2,'rgb':[1,2,3],'answer':'WEST'}]
        for shape in invalid:
            with self.assertRaises(ValueError):render_scene([shape],camera)
        bad=deepcopy(camera);bad['matrix']=[[1,2,0],[2,4,0]]
        with self.assertRaises(ValueError):render_scene([],bad)
        with self.assertRaises(ValueError):render_scene([],camera,noise=True)
        with self.assertRaises(ValueError):render_scene([],camera,noise_seed=-1)


if __name__=='__main__':unittest.main()
