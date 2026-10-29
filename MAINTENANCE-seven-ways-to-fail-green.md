# Seven ways to fail green

Maintenance document. The seven patterns that did damage in this repository
and that **reappeared within a single working day**. They are not bugs: they
are ways of building that read well, pass the tests, and do not hold up what
they appear to.

Each one comes with the times it was seen, not because those cases matter —
they are fixed and archived— but as proof that the pattern is real and not a
theoretical precaution.

Written 2026-09-20.

---

## 1. A requirement with no way to answer it

A machine asks for something and provides no way to give it. Whoever uses it
has two ways out: invent a value to get through, or stay stuck.

**They always choose to invent.** And the invented value ends up looking like a
decision taken.

> It is the glued needle: the mechanic fixes the fuel gauge, but to close the
> job glues the needle at "half tank". The gauge works and the tank lies
> forever.

**Seen twice the same day.** A change made writing a block require knowing
which section it comes from, without building anything that recorded it: the
only path was editing by hand a file that is distributed. Later, another one
required a root declaration that also had no verb to write it, and the hole was
plugged by an agent writing JSON from outside.

**The test:** stand at the moment the machine refuses and ask *"what do I answer
this with?"*. If the answer is "editing a file" or "an agent writes it", the key
does not exist.

**The fix has three parts and none is superfluous:** that there is a place to
put it, that there is a **way** to put it —a verb, not an editor—, and that the
refusal **names** that way.

---

## 2. A guard that cannot fire

A present guard and a reachable guard read identically. The code is there, the
test passes, the roster lists it — and it never runs.

**Four ways for that to happen, all four seen here:**

- **Wired only to a read-only verb.** The report warns and the path that writes
  goes straight past. Nine measured cases in this repo so far; there was almost
  a tenth.
- **Ordered after something stricter.** A concession check placed behind the
  structural rejection never gets to fire: the other one intercepts everything
  first.
- **Invisible to the deriver.** The roster is built by a static scan.
  Re-raising a rejection with a variable instead of a literal text makes the
  guard work and the roster never see it.
- **With a formula that does not discriminate.** A mutation tested against a
  case where the correct and the broken version give the same number proves
  nothing. It took a case of three to separate them.

**The test, and it is the only one:** break the guard and watch the test turn
red. A test that passes against the healthy engine says nothing about whether
the guard holds.

And two traps when running mutations: a mutation of the same size can reuse
the old bytecode, so the mutated code never runs; and `git diff --stat` proves
nothing about an unversioned file.

---

## 3. Prose that outlives its mechanism

A document asserts a behaviour. The behaviour changes, or was never
implemented. The document is still there, asserting it.

**A document does not execute.** That is why it does not find out.

**Four cases in one day, and the fact that matters most: all four were found by
a later change going to rely on them. None was found by its own
verification.** An archived design promised that a function returned something
its signature declared `None`. A ticked task said a datum came out through three
verbs and it came out through none. A proposal asserted an input that the
design never routed. A verb count was born stale the day it was "fixed".

**And the case that deceives most: prose that tells the truth TODAY.** A
decision that cannot be measured yet —because it lacks a datum that does not
exist yet— is written as a declared ruling, with what would falsify it. That is
done right. But it stays in a document, and a document does not find out the
day that datum appears. The note remains true, nobody contradicts it, and
nobody looks at it again either.

The fix is to turn the wait into a **witness**: a test that reads the
precondition and passes **only while it remains unmet**. The day it is met it
turns red and says what is owed. It costs ten lines.

> A pending item that depends on something appearing is not kept in prose. It
> is kept in something that runs and checks whether it has appeared.

And like any guard: prove it can fire. A witness that passes because the
precondition was never met reads the same as one that cannot fail.

**The two rules:**

> Do not inherit any claim from a previous artifact without measuring it again.
> If you are going to rely on something working, run it.

> The proof that something is visible is **running the verb and reading what it
> prints**. Asserting that a field exists on an object is exactly the test that
> let a half-done ticked task through.

---

## 4. Deciding instead of asking

A decision that belongs to a person ends up being taken by a machine, an agent
reading prose, or a conversation set up to unblock something else.

It happens without bad intent: someone needs to keep going, the decision looks
obvious, and it ends up taken.

**Three forms, all three seen:**

- **An agent derives and records.** It read a contract's prose, deduced a value
  and wrote it. Nobody chose it.
- **I relayed the invention as a question.** Instead of reading that the
  machine had forced an invention, I took the invention to the owner to ratify
  it.
- **A concession out of courtesy.** An agent that accepts the owner's proposal
  because it is the owner's, not because it is better.

**The rule:** a decision is taken **by using** the skill, never by editing a
file, never in a conversation set up to unblock a repair. Someone saying "yes"
while looking at a table is not the same as the machine stopping them at the
right moment, with the material in front of them.

**And the structural corollary:** if a negotiation's artifact carries a field
saying whose each proposal is, the machine cannot verify it — it is a claim of
authority disguised as schema. It should not carry one, and both should be
scored the same.

---

## 5. A chosen number, presented as measured

A threshold, a floor, a count. It is chosen by judgment, written without a
mark, and six months later nobody knows it was a decision. A number nobody can
dispute is a number nobody measured.

**Both sides, both seen:**

- **Chosen and declared as such.** A repetition threshold was set at 16 because
  the original 8 had been calibrated against papers by other authors and did
  not transfer. It was written down that it is a ruling, with what would
  falsify it, and the floor is **reported in every response** so it can be
  contested.
- **Measured when it could be measured.** A Python version floor was derived by
  scanning which constructs the code uses, instead of choosing a reasonable
  number.

**The rule:** if it can be measured, measure it. If not, say it is a ruling and
write what would change it. And when the number governs a behaviour, **report
it in the output**: that is what makes it disputable the day there is data.

And a way to sustain it that works better than goodwill: if a sentence has to
tell the truth in four places, make it **a single constant** with a test that
requires the four to match. Saying it wrong becomes a red test instead of
something a reviewer has to notice.

---

## 6. Fixing the instance and leaving the class

A defect is found, fixed where it was seen, and the same shape stays standing in
two other places.

**Three times:**

- A function that normalized text let equations through. There were **two
  copies** with the same error, and the second fed a different guard.
- The vocabulary guard derived its forbidden list by reading **a single**
  product root. The names of the others were invisible to it, and that is why
  fourteen lines made it into distributed files with the whole suite green.
- A pinned count protected one skill and not its siblings.

**The question, every time:** *what else has this same shape?*

**And the right fix is not touching both places: it is having something derived
find them.** A list of two goes stale when someone writes the third. A sweep
that introspects every module does not.

---

## 7. A test that ratifies a decision instead of verifying a property

A test counts how many elements a list has, or transcribes which ones they are.
It passes. And from that moment the list **cannot be changed without turning it
red** — even though nobody ever decided it should be that list.

The test stops protecting a behaviour and starts **guarding a choice**. Worse:
the test's name states it as if it were a requirement.

**The case:** a skill declared three source folders. A test was named *"three
sources are declared: the data paper and the proposal are mandatory, the field
benchmark is not"* and asserted `sources.length === 3`. When the owner said
*"I never authorized that benchmark"*, removing it turned the test red. The
test was not defending a property of the skill: it was defending that someone,
once, had written three.

> It is the glued needle again, but the other way around: here the datum is not
> faked so the gauge passes — the gauge is bolted down so the datum cannot
> move.

**How to tell them apart.** Ask the test *"what would break in production if
this were different?"*

- *"Nothing, it would be another equally valid decision"* → it is ratifying.
- *"The engine would read a source that does not exist"* → it is verifying.

**The fix is not deleting the test, it is changing what it asserts.** Instead
of counting elements, assert the property the list must satisfy no matter what:
that every declared source exists, that the source that bounds the claims is
one of the declared ones and is mandatory, that no path escapes the
repository. Those stay true with two sources, with three or with seven — and
keep turning red when something really breaks.

**And the corollary, which is the hardest:** a count in a test is the place
where a decision not taken becomes indistinguishable from a requirement. If the
number has to be there, the test should say **why it is that number**, and the
comment should name who decided it and when. A count without that line is an
anonymous decision with the force of law.

---

## How they look together

The seven share a root: **something reads as a guarantee without being one.**

```
1  a requirement reads as a rule             and forces invention
2  a guard reads as protection               and cannot fire
3  a document reads as the state             and describes another
4  a value reads as a decision               and a machine put it there
5  a number reads as measured                and was chosen
6  a fix reads as closed                     and the class stays open
7  a test reads as a requirement             and guards a choice
```

That is why none is detected by reading. The six are detected **by running**:
the verb and its output, the mutation and its red, the document against the
code, the refusal against what there is to answer it.

---

## What to ask before considering a change closed

- Does anything this change **requires** have a way to be answered by using the
  skill?
- Each new rejection: did I see it turn **red** under mutation, or does it only
  pass green?
- Is any rejection reachable only from a verb that does not write?
- Does any document I touched assert something I did not run?
- Was any decision in this change taken by an agent, or by me, instead of by
  the person using the skill?
- Is any new number presented as measured without being so?
- The defect I fixed: does it have siblings with the same shape? And is what
  finds them derived, or is it a list?
- For each new test that counts or enumerates: what would break in production if
  the number were different? If the answer is "nothing", it is ratifying a
  decision, not verifying a property.
