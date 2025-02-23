"""Beam search implementation in PyTorch."""
#
#
#         hyp1#-hyp1---hyp1 -hyp1
#                 \             /
#         hyp2 \-hyp2 /-hyp2#hyp2
#                               /      \
#         hyp3#-hyp3---hyp3 -hyp3
#         ========================
#
# Takes care of beams, back pointers, and scores.

# Code borrowed from PyTorch OpenNMT example
# https://github.com/pytorch/examples/blob/master/OpenNMT/onmt/Beam.py

import torch


class Beam(object):
    """Ordered beam of candidate outputs."""

    def __init__(self, size, vocab, hidden, device=torch.device("cuda:0")):
        """Initialize params."""
        self.size = size
        self.done = False
        # self.pad = vocab['<pad>']
        self.bos = vocab['<s>']
        self.eos = vocab['</s>']
        self.device = device
        self.tt = torch.cuda if device.type == "cuda" else torch
        # The score for each translation on the beam.
        self.scores = self.tt.FloatTensor(size, device=self.device).zero_()

        # The backpointers at each time-step.
        self.prevKs = []

        # The outputs at each time-step.
        self.nextYs = [self.tt.LongTensor(size, device=self.device).fill_(self.eos)]
        self.nextYs[0][0] = self.bos

        # the hidden state at current time-step
        hidden = hidden.view(1, 1, -1)
        self.hidden = hidden.expand((1, size, hidden.shape[2]))

        # The attentions (matrix) for each time.
        self.attn = []

    # Get the outputs for the current timestep.
    def get_current_word(self):
        """Get state of beam."""
        return self.nextYs[-1]

    def get_hidden_state(self):
        return self.hidden.contiguous()

    # Get the backpointers for the current timestep.
    def get_prev_word(self):
        """Get the backpointer to the beam at this step."""
        return self.prevKs[-1]

    #  Given log_prob over words for every last beam `wordLk` and attention
    #   `attnOut`: Compute and update the beam search.
    #
    # Parameters:
    #
    #     * `wordLk`- probs of advancing from the last step (K x words)
    #     * `attnOut`- attention at the last step
    #
    # Returns: True if beam search is complete.

    def advance_(self, log_probs, hidden):
        if self.done:
            return True

        """Advance the beam."""
        log_probs = log_probs.squeeze() # k*V
        num_words = log_probs.shape[-1]

        # Sum the previous scores.
        if len(self.prevKs) > 0:
            beam_lk = log_probs + self.scores.unsqueeze(1).expand_as(log_probs)
        else:
            beam_lk = log_probs[0]

        flat_beam_lk = beam_lk.view(-1)

        bestScores, bestScoresId = flat_beam_lk.topk(self.size, 0, True, True)
        self.scores = bestScores

        # bestScoresId is flattened beam x word array, so calculate which
        # word and beam each score came from
        prev_k = bestScoresId // num_words
        self.prevKs.append(prev_k)
        self.nextYs.append(bestScoresId - prev_k * num_words)
        
        # print(prev_k)

        self.hidden = hidden[:,prev_k,:] # hidden: 1 * k * hid_dim

        # End condition is when top-of-beam is EOS.
        if self.nextYs[-1][0] == self.eos:
            self.done = True

    def sort_best(self):
        """Sort the beam."""
        return torch.sort(self.scores, 0, True)

    # Get the score of the best in the beam.
    def get_best(self):
        """Get the most likely candidate."""
        scores, ids = self.sort_best()
        return scores[1], ids[1]

    # Walk back to construct the full hypothesis.
    #
    # Parameters.
    #
    #     * `k` - the position in the beam to construct.
    #
    # Returns.
    #
    #     1. The hypothesis
    #     2. The attention at each time step.
    def get_hyp(self, k):
        """Get hypotheses."""
        hyp = []
        # print(len(self.prevKs), len(self.nextYs), len(self.attn))
        for j in range(len(self.prevKs) - 1, -1, -1):
            hyp.append(self.nextYs[j + 1][k])
            k = self.prevKs[j][k]

        return hyp[::-1]

