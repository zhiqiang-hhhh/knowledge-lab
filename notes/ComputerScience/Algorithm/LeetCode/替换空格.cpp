void replaceBlank(char string[], int length) {
  if (string == nullptr || length <= 0) return;

  int oriLen = 0;
  int cntBlank = 0;
  for (int i = 0; i < length; ++i) {
    oriLen++;
    if (string[i] == ' ') cntBlank++;
  }

  int newLen = oriLen + 2 * cntBlank;
  if (newLen > length) return;

  int idxleft = oriLen;
  int idxright = newLen;
  while (idxleft >= 0 && idxright > idxleft) {
    if (string[idxleft] == ' ') {
      string[idxright--] = '0';
      string[idxright--] = '2';
      string[idxright--] = '%';
      continue;
    }
    string[idxright] = string[idxleft];
    --idxright;
    --idxleft;
  }
}