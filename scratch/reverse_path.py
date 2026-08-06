path = "DLLDLLLLLLLLLLLLDLDDLLLLLLLLLLLLLLLLLLLLLLLDDDDDDDDDDDRRRRRRRUUUURRRRRRRRRRRU"

def reverse_path(p):
    rev = p[::-1]
    mapping = {'U': 'D', 'D': 'U', 'L': 'R', 'R': 'L'}
    return ''.join(mapping[c] for c in rev)

print("CENTER_TO_ROUTE15 =", reverse_path(path))
