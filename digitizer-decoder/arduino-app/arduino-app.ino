/*
  Digitizer simulator for digitizer-decoder.
  Reads potentiometer on A0 and streams weight as: [00000] … [50000]

  Fixes unstable "converter" readings when the pot is not moved:
  - multi-sample ADC average
  - hysteresis so small noise does not change the published value
  - fixed 5-digit zero-padded frame
*/

const int POT_PIN = A0;
const int ADC_SAMPLES = 20;       // average this many reads
const long HYSTERESIS_KG = 20;    // ignore changes smaller than this (kg)
const long WEIGHT_MAX_KG = 50000; // map full-scale pot → 50000 kg
const unsigned long SEND_MS = 250;

long lastPublishedKg = -1;

void setup() {
  Serial.begin(9600);
  pinMode(POT_PIN, INPUT);
  // Discard a few warm-up samples
  for (int i = 0; i < 8; i++) {
    analogRead(POT_PIN);
    delay(2);
  }
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
  // Arduino Uno ADC is 0..1023 (not 1024)
  long kg = map(potVal, 0, 1023, 0, WEIGHT_MAX_KG / 10) * 10L;
  if (kg < 0) kg = 0;
  if (kg > WEIGHT_MAX_KG) kg = WEIGHT_MAX_KG;
  return kg;
}

long applyHysteresis(long candidateKg) {
  if (lastPublishedKg < 0) {
    return candidateKg;
  }
  long delta = candidateKg - lastPublishedKg;
  if (delta < 0) delta = -delta;
  // Pot not moved enough → keep previous stable value
  if (delta < HYSTERESIS_KG) {
    return lastPublishedKg;
  }
  return candidateKg;
}

void printWeightFrame(long kg) {
  // Always exactly 5 digits: [00000] … [50000]
  char frame[8];
  snprintf(frame, sizeof(frame), "[%05ld]", kg);
  Serial.print(frame);
}

void loop() {
  int potVal = readPotAveraged();
  long rawKg = potToWeightKg(potVal);
  long stableKg = applyHysteresis(rawKg);
  lastPublishedKg = stableKg;

  printWeightFrame(stableKg);
  delay(SEND_MS);
}
