import cv2
import numpy as np
import copy


def generatePseudoScribble(scribble, gap, isUp):
    psuedoScribble = []
    if isUp:
        gap = -gap
    for i in range(len(scribble)):
        psuedoScribble.append([scribble[i][0], scribble[i][1] + gap])
    return psuedoScribble


def compute_lower_seams(energy, regions, initPoints, endPoints):
    energy = energy.copy()
    length = energy.shape[1]
    max_height = 0
    for region in regions:
        extent = np.max(region[:, 1]) - np.min(region[:, 1]) + 1
        if extent > max_height:
            max_height = extent

    regions_ = copy.deepcopy(regions)
    max_height += 2

    deck = np.zeros((length, len(regions_), max_height))
    for i in range(len(regions_)):
        regions_[i][:, 1] = regions_[i][:, 1] - np.min(regions_[i][:, 1]) + 1
        canvas = np.zeros((max_height, length), dtype=np.int32)
        cv2.fillPoly(canvas, [regions_[i]], color=[255])
        canvas = canvas.T
        deck[:, i, :] = canvas

    white_area = np.full((deck.shape[2], energy.shape[1]), 255, dtype=np.int32)
    energy = np.concatenate((energy, white_area))
    highest_points = np.empty((deck.shape[1]), dtype=np.int32)
    for i in range(deck.shape[1]):
        highest_points[i] = np.min(regions[i][:, 1])
    highest_points[highest_points < 0] = 0
    energy_deck = np.empty_like(deck, dtype=np.int32)
    for i in range(deck.shape[1]):
        energy_deck[:, i, :] = energy[
            max((highest_points[i] - 1, 0)): max((highest_points[i] - 1, 0)) + deck.shape[2]
        ].T
    energy_deck[deck == 0] = 255

    dp_deck = np.zeros_like(deck, dtype=np.int64)
    dp_deck[-1] = energy_deck[-1]
    dp_deck[-1, :, 0] = 10000000
    dp_deck[-1, :, -1] = 10000000
    choices = np.zeros_like(deck, dtype=np.int8)
    for col in range(deck.shape[0] - 2, -1, -1):
        options = np.array(
            [
                dp_deck[col + 1, :, 0:-2],
                dp_deck[col + 1, :, 1:-1],
                dp_deck[col + 1, :, 2:],
            ]
        )
        choice = np.argmin(options, axis=0)
        choice_energies = np.min(options, axis=0)
        choices[col, :, 1:-1] = choice
        dp_deck[col, :, 1:-1] = energy_deck[col, :, 1:-1] + choice_energies
        dp_deck[col, :, 0] = 10000000
        dp_deck[col, :, -1] = 10000000
        

    seams = np.full((deck.shape[0], deck.shape[1]), -10000000, dtype=np.int32)
    seams[initPoints[:, 0], range(deck.shape[1])] = initPoints[:, 1] - highest_points + 1
    for i in range(deck.shape[1]):
        for j in range(initPoints[i][0] + 1, endPoints[i][0] + 1):
            seams[j][i] = seams[j - 1][i] - 1 + choices[j - 1][i][seams[j - 1][i]]

    return seams + highest_points - 1


def compute_upper_seams(energy, regions, initPoints, endPoints):
    energy = energy.copy()
    length = energy.shape[1]
    max_height = 0
    for region in regions:
        # print(f"{region}")
        extent = np.max(region[:, 1]) - np.min(region[:, 1]) + 1
        if extent > max_height:
            max_height = extent

    max_height += 2

    regions_ = copy.deepcopy(regions)

    deck = np.zeros((length, len(regions_), max_height))
    for i in range(len(regions_)):
        regions_[i][:, 1] = regions_[i][:, 1] - np.min(regions_[i][:, 1]) + 1
        canvas = np.zeros((max_height, length), dtype=np.int32)
        cv2.fillPoly(canvas, [regions_[i]], color=[255])
        canvas = canvas.T
        deck[:, i, :] = canvas

    white_area = np.full((deck.shape[2], energy.shape[1]), 255, dtype=np.int32)
    energy = np.concatenate((energy, white_area))
    highest_points = np.empty((deck.shape[1]), dtype=np.int32)
    for i in range(deck.shape[1]):
        highest_points[i] = np.min(regions[i][:, 1])
    highest_points[highest_points < 0] = 0
    energy_deck = np.empty_like(deck, dtype=np.int32)
    for i in range(deck.shape[1]):
        try:
            energy_deck[:, i, :] = energy[
                max((highest_points[i] - 1, 0)): max((highest_points[i] - 1, 0)) + deck.shape[2]
            ].T
        except Exception as e:
            print(e)
            print(f"{max(highest_points[i] - 1, 0)}")
            print(f"{max(highest_points[i] - 1, 0) + deck.shape[2]}")
            print(energy[
                max(highest_points[i] - 1, 0): max(highest_points[i] - 1, 0) + deck.shape[2]
            ].shape)
            exit()
    energy_deck[deck == 0] = 255

    visdeck = energy_deck.copy()
    visdeck = np.transpose(visdeck, (1, 2, 0))

    ### DEBUG - commented
    # for i, card in enumerate(visdeck):
    #    cv2.imwrite(f"energy{i}.jpg", card)

    dp_deck = np.zeros_like(deck, dtype=np.int64)
    dp_deck[-1] = energy_deck[-1]
    dp_deck[-1, :, 0] = 10000000
    dp_deck[-1, :, -1] = 10000000
    choices = np.zeros_like(deck, dtype=np.int8)
    for col in range(deck.shape[0] - 2, -1, -1):
        options = np.array(
            [
                dp_deck[col + 1, :, 2:],
                dp_deck[col + 1, :, 1:-1],
                dp_deck[col + 1, :, 0:-2],
            ]
        )
        choice = np.argmin(options, axis=0)
        choice_energies = np.min(options, axis=0)
        choices[col, :, 1:-1] = choice
        dp_deck[col, :, 1:-1] = energy_deck[col, :, 1:-1] + choice_energies
        dp_deck[col, :, 0] = 10000000
        dp_deck[col, :, -1] = 10000000

    seams = np.full((deck.shape[0], deck.shape[1]), -10000000, dtype=np.int32)
    # seams[0] = np.argmin(dp_deck[0], axis=1)
    # for col in range(1, deck.shape[0]):
    #     seams[col] = (
    #         seams[col - 1]
    #         + 1
    #         - choices[col - 1, range(choices.shape[1]), list(seams[col - 1])]
    #     )
    seams[initPoints[:, 0], range(deck.shape[1])] = initPoints[:, 1] - highest_points + 1
    for i in range(deck.shape[1]):
        for j in range(initPoints[i][0] + 1, endPoints[i][0] + 1):
            seams[j][i] = seams[j - 1][i] + 1 - choices[j - 1][i][seams[j - 1][i]]

    return seams + highest_points - 1

