/*
  Digitizer simulator for digitizer-decoder.

  Weight source:
    - Potentiometer on A0 → maps to WEIGHT_MIN_KG .. WEIGHT_MAX_KG
    - GPIO A2 (INPUT_PULLUP): pressed (LOW) → force 0 kg; released → pot value
    - GPIO A3 (INPUT_PULLUP): pressed (LOW) → insert '-' at a random place
      in the digit field (e.g. [500-], [-400], [30-0]) for -ve parser testing

  All formats keep non-weight text fixed; the weight token is a fixed-width
  field (space- or zero-padded) so suffixes like " G Wt:" stay aligned.

  Method select (ground one pin) — format only, no static weight:
    D2  → STX/ETX:        <STX><space>±######<ETX><CR><LF>
    D3  → ST,GS:          ST,GS,±#######kg
    D4  → Method 2:       " ±##### kg    G 000000 A"
    D5  → Method 3:       garbled "G … A"
    D6  → Method 4:       "Wt:    ±##### G Wt:" + CR/LF
    D7  → Method 5:       [±#####] bracket frame
    D8  → Method 6:       leading number + garbage
    D9  → Method 7:       plain ASCII digits
    D10 → ST,GS (same as D3)
    D13 → STX/ETX (same as D2)

  Baud: 9600
*/

const uint32_t BAUD_RATE = 9600;

const int POT_PIN = A0;
const uint8_t PIN_ZERO_FORCE = A2;      // pressed → send 0 kg
const uint8_t PIN_MINUS_SCRAMBLE = A3;  // pressed → random '-' placement in digits

const uint8_t PIN_METHOD_D2  = 2;
const uint8_t PIN_METHOD_D3  = 3;
const uint8_t PIN_METHOD_D4  = 4;
const uint8_t PIN_METHOD_D5  = 5;
const uint8_t PIN_METHOD_D6  = 6;
const uint8_t PIN_METHOD_D7  = 7;
const uint8_t PIN_METHOD_D8  = 8;
const uint8_t PIN_METHOD_D9  = 9;
const uint8_t PIN_METHOD_D10 = 10;
const uint8_t PIN_METHOD_D13 = 13;

const int ADC_SAMPLES = 20;
const long HYSTERESIS_KG = 20;
const long WEIGHT_MIN_KG = -4000;   // pot low end (allows -ve simulation)
const long WEIGHT_MAX_KG = 50000;   // pot high end
const unsigned long SEND_INTERVAL_MS = 250;

unsigned long lastSendMs = 0;
long lastPublishedKg = 0;
bool hasPublishedKg = false;

void setup() {
  Serial.begin(BAUD_RATE);
  randomSeed(analogRead(A1) ^ micros());

  pinMode(POT_PIN, INPUT);
  pinMode(PIN_ZERO_FORCE, INPUT_PULLUP);
  pinMode(PIN_MINUS_SCRAMBLE, INPUT_PULLUP);

  pinMode(PIN_METHOD_D2, INPUT_PULLUP);
  pinMode(PIN_METHOD_D3, INPUT_PULLUP);
  pinMode(PIN_METHOD_D4, INPUT_PULLUP);
  pinMode(PIN_METHOD_D5, INPUT_PULLUP);
  pinMode(PIN_METHOD_D6, INPUT_PULLUP);
  pinMode(PIN_METHOD_D7, INPUT_PULLUP);
  pinMode(PIN_METHOD_D8, INPUT_PULLUP);
  pinMode(PIN_METHOD_D9, INPUT_PULLUP);
  pinMode(PIN_METHOD_D10, INPUT_PULLUP);
  pinMode(PIN_METHOD_D13, INPUT_PULLUP);

  for (int i = 0; i < 8; i++) {
    analogRead(POT_PIN);
    delay(2);
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs < SEND_INTERVAL_MS) {
    return;
  }
  lastSendMs = now;

  int method = detectSelectedMethod();
  if (method == 0) {
    // No method pin grounded — stay quiet
    return;
  }

  long kg = readWeightKg();

  switch (method) {
    case 1:  sendFmt_StxEtx(kg);      break;  // D2
    case 2:  sendFmt_STGS(kg);        break;  // D3
    case 3:  sendFmt_KgFormat(kg);    break;  // D4
    case 4:  sendFmt_GAFormat(kg);    break;  // D5
    case 5:  sendFmt_WtFormat(kg);    break;  // D6
    case 6:  sendFmt_Bracket(kg);     break;  // D7
    case 7:  sendFmt_Prefix(kg);      break;  // D8
    case 8:  sendFmt_PlainAscii(kg);  break;  // D9
    case 9:  sendFmt_STGS(kg);        break;  // D10
    case 10: sendFmt_StxEtx(kg);      break;  // D13
  }
}

// Return 1..10 from grounded pin; 0 if none
int detectSelectedMethod() {
  if (digitalRead(PIN_METHOD_D2) == LOW)  return 1;
  if (digitalRead(PIN_METHOD_D3) == LOW)  return 2;
  if (digitalRead(PIN_METHOD_D4) == LOW)  return 3;
  if (digitalRead(PIN_METHOD_D5) == LOW)  return 4;
  if (digitalRead(PIN_METHOD_D6) == LOW)  return 5;
  if (digitalRead(PIN_METHOD_D7) == LOW)  return 6;
  if (digitalRead(PIN_METHOD_D8) == LOW)  return 7;
  if (digitalRead(PIN_METHOD_D9) == LOW)  return 8;
  if (digitalRead(PIN_METHOD_D10) == LOW) return 9;
  if (digitalRead(PIN_METHOD_D13) == LOW) return 10;
  return 0;
}

long readWeightKg() {
  // A2 pressed (LOW) → force zero regardless of pot
  if (digitalRead(PIN_ZERO_FORCE) == LOW) {
    lastPublishedKg = 0;
    hasPublishedKg = true;
    return 0;
  }

  int potVal = readPotAveraged();
  long rawKg = potToWeightKg(potVal);
  long stableKg = applyHysteresis(rawKg);
  lastPublishedKg = stableKg;
  hasPublishedKg = true;
  return stableKg;
}

int readPotAveraged() {
  long sum = 0;
  for (int i = 0; i < ADC_SAMPLES; i++) {
    sum += analogRead(POT_PIN);
    delayMicroseconds(300);
  }
  return (int)(sum / ADC_SAMPLES);
}

long potToWeightKg(int potVal) {
  // Uno ADC 0..1023 → WEIGHT_MIN_KG .. WEIGHT_MAX_KG
  long kg = map((long)potVal, 0L, 1023L, WEIGHT_MIN_KG, WEIGHT_MAX_KG);
  if (kg < WEIGHT_MIN_KG) kg = WEIGHT_MIN_KG;
  if (kg > WEIGHT_MAX_KG) kg = WEIGHT_MAX_KG;
  return kg;
}

long applyHysteresis(long candidateKg) {
  if (!hasPublishedKg) {
    return candidateKg;
  }
  long delta = candidateKg - lastPublishedKg;
  if (delta < 0) delta = -delta;
  if (delta < HYSTERESIS_KG) {
    return lastPublishedKg;
  }
  return candidateKg;
}

long clampAbsDigits(long kg, long maxAbs) {
  long a = (kg < 0) ? -kg : kg;
  if (a > maxAbs) a = maxAbs;
  return (kg < 0) ? -a : a;
}

bool minusScrambleActive() {
  return digitalRead(PIN_MINUS_SCRAMBLE) == LOW;
}

/*
 * Build weight token only (no outer padding).
 * Normal: leading '-' when weightKg < 0.
 * A3 pressed: '-' inserted at a random place in/around the digits.
 */
void buildWeightToken(char *out, size_t outSize, long weightKg, int digitWidth, bool zeroPad) {
  long mag = (weightKg < 0) ? -weightKg : weightKg;
  char digits[16];

  if (zeroPad && digitWidth > 0) {
    char fmt[12];
    snprintf(fmt, sizeof(fmt), "%%0%dld", digitWidth);
    snprintf(digits, sizeof(digits), fmt, mag);
  } else {
    snprintf(digits, sizeof(digits), "%ld", mag);
  }

  if (!minusScrambleActive()) {
    if (weightKg < 0) {
      snprintf(out, outSize, "-%s", digits);
    } else {
      snprintf(out, outSize, "%s", digits);
    }
    return;
  }

  int n = (int)strlen(digits);
  int pos = (int)random(0, n + 1);
  size_t i = 0;
  for (int d = 0; d < pos && i + 1 < outSize; d++) {
    out[i++] = digits[d];
  }
  if (i + 1 < outSize) {
    out[i++] = '-';
  }
  for (int d = pos; d < n && i + 1 < outSize; d++) {
    out[i++] = digits[d];
  }
  out[i] = '\0';
}

/*
 * Right-align token into a fixed fieldWidth with leading spaces.
 * Keeps non-weight text (prefixes/suffixes) in a fixed column.
 * If token is longer than fieldWidth, it is copied truncated to fit.
 */
void padWeightField(char *out, size_t outSize, const char *token, int fieldWidth) {
  if (fieldWidth < 1 || (size_t)fieldWidth + 1 > outSize) {
    snprintf(out, outSize, "%s", token);
    return;
  }
  int len = (int)strlen(token);
  if (len >= fieldWidth) {
    // Prefer rightmost fieldWidth chars (keeps digits / trailing '-')
    int start = len - fieldWidth;
    memcpy(out, token + start, (size_t)fieldWidth);
    out[fieldWidth] = '\0';
    return;
  }
  int pad = fieldWidth - len;
  for (int i = 0; i < pad; i++) {
    out[i] = ' ';
  }
  memcpy(out + pad, token, (size_t)len);
  out[fieldWidth] = '\0';
}

/*
 * Fixed-width weight field: build token, then space-pad to fieldWidth.
 * digitWidth/zeroPad control the numeric body; fieldWidth locks columns.
 */
void formatWeightField(char *out, size_t outSize, long weightKg,
                       int digitWidth, bool zeroPad, int fieldWidth) {
  char token[20];
  buildWeightToken(token, sizeof(token), weightKg, digitWidth, zeroPad);
  if (fieldWidth > 0) {
    padWeightField(out, outSize, token, fieldWidth);
  } else {
    snprintf(out, outSize, "%s", token);
  }
}

/*
 * STX/ETX frame (D2 / D13)
 *   <STX><space>#######<ETX><CR><LF>   (7-char field: optional sign + 6 digits)
 */
void sendFmt_StxEtx(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 6, true, 7);
  Serial.write(0x02);
  Serial.write(' ');
  Serial.print(field);
  Serial.write(0x03);
  Serial.write('\r');
  Serial.write('\n');
}

/*
 * ST,GS format (D3 / D10)
 *   ST,GS,+#######kg / ST,GS,-#######kg  (sign column fixed, then 7 digits)
 *   A3 scramble: ST,GS,########kg       (8-char field, no separate +/-)
 */
void sendFmt_STGS(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 9999999L);
  char field[16];
  if (minusScrambleActive()) {
    formatWeightField(field, sizeof(field), weightKg, 7, true, 8);
    Serial.print("ST,GS,");
    Serial.print(field);
    Serial.print("kg");
  } else {
    // Force magnitude-only token, then fixed sign + 7 zero digits
    long mag = (weightKg < 0) ? -weightKg : weightKg;
    char digits[12];
    snprintf(digits, sizeof(digits), "%07ld", mag);
    char sign = (weightKg < 0) ? '-' : '+';
    Serial.print("ST,GS,");
    Serial.write(sign);
    Serial.print(digits);
    Serial.print("kg");
  }
}

/*
 * " kg" format (D4)
 *   " " + 9-char weight + " kg    G 000000 A"
 */
void sendFmt_KgFormat(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 0, false, 9);
  Serial.print(" ");
  Serial.print(field);
  Serial.print(" kg    G 000000 A");
}

/*
 * Garbled G … A format (D5)
 *   prefix + 7-char weight + " A"
 */
void sendFmt_GAFormat(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 6, true, 7);
  Serial.print(",  ´66.0 ëç    G ");
  Serial.print(field);
  Serial.print(" A");
}

/*
 * Wt: format (D6) — matches site alignment:
 *   Wt:    10727 G Wt:
 *   Wt:     9829 G Wt:
 *   Wt:      645 G Wt:
 */
void sendFmt_WtFormat(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 0, false, 9);
  Serial.print("Wt:");
  Serial.print(field);
  Serial.print(" G Wt:");
  Serial.write('\r');
  Serial.write('\n');
}

/*
 * Bracket frame (D7)
 *   [#####] / [-####] / A3 scrambled — always 6 chars inside brackets
 */
void sendFmt_Bracket(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 99999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 5, true, 6);
  Serial.print("[");
  Serial.print(field);
  Serial.print("]");
}

/*
 * Leading-number + garbage (D8)
 *   9-char weight + fixed garbage suffix
 */
void sendFmt_Prefix(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 0, false, 9);
  Serial.print(field);
  Serial.print("ePG%w");
  Serial.write((uint8_t)0xB0);
  Serial.write((uint8_t)0xB0);
}

/*
 * Plain ASCII digits (D9)
 *   8-char field (optional sign + 7 zero-padded digits)
 */
void sendFmt_PlainAscii(long weightKg) {
  weightKg = clampAbsDigits(weightKg, 9999999L);
  char field[16];
  formatWeightField(field, sizeof(field), weightKg, 7, true, 8);
  Serial.print(field);
}
