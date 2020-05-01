## Delay siblings — an Anki script

When reviewing a card, reschedule its siblings if they are set to appear
too soon. Consider that you've got two cards on a single note, “A → B”
and “B → A”, that both have an interval of several months but are due
to appear days apart. If you review one of these cards today, your
reviewing the sibling card tomorrow will make little sense and will just
waste your time.

This script is especially useful when you are reviewing a deck that
hasn't been touched for a while and thus has a lot of siblings due
simultaneously.

This script displays a notification whenever it's rescheduling a card,
unless you disable it, for example:

![notification example](notification.png)

### How it works

This script reschedules siblings when Anki displays an answer to a card.
The only thing that is taken into account is the sibling's interval (the
number of days between the last review and the next one). The interval
of the current card and your answer are not considered. The siblings are
not rescheduled if they appear after the minimum new interval. The
following table contains some minimum and maximum delays for siblings,
taken from the [function used](https://www.desmos.com/calculator/fnh882qnd1).



|     Interval  | 1 sibling      | 2 siblings    |
|     --:       | --:            | --:           |
|   0 to 1 days |         0 days |        0 days |
|   2 to 4 days |         1 days |   0 to 1 days |
|   5 to 6 days |    1 to 2 days |        1 days |
|  7 to 10 days |    2 to 3 days |   1 to 2 days |
| 12 to 14 days |    3 to 4 days |   2 to 3 days |
| 16 to 20 days |    4 to 6 days |   2 to 5 days |
|       30 days |    6 to 8 days |   4 to 5 days |
|       60 days |  10 to 13 days |   7 to 9 days |
|       90 days |  13 to 17 days |  9 to 11 days |
|      180 days |  19 to 25 days | 13 to 17 days |
|      360 days |  28 to 37 days | 19 to 24 days |
|      720 days |  40 to 52 days | 27 to 35 days |
|     1500 days |  57 to 74 days | 38 to 49 days |
|     3000 days | 78 to 101 days | 52 to 67 days |


### Settings

You can find the following 2 options in the Tools menu:

* Enable sibling delaying. Enables or disables the script for current
deck.
* Don’t notify if a card is delayed by less than 2 weeks. Since only the
interval of the sibling is considered, the current card or other siblings
can become due close to the sibling. To prevent notification spam, check
this option.
