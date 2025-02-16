---
layout: post
title:  Principles for Writing Maintainable Code
date:   2020-09-12 12:00:00
<!-- categories: jekyll update -->
<!-- tags: ruby rails -->
author: Max Lukin
<!-- excerpt: How to create your own simple blog -->
---
Applications always change, and writing maintainable code is very important in software engineering. Here in Lukin.io we decided to gather most important best practices with Ruby on Rails, examples and definations in one place.

In my work i'm using principles like: [DRY (Don't repeat youself)][dry]{:target="_blank"}, [KISS (Keep it simple, stupid)][kiss]{:target="_blank"}, [YAGNI (You aren't gonna need it)][yagni]{:target="_blank"} and [Eating your own dog food][eyodf]{:target="_blank"}, but in this post i'll highlight most important ones.

First one is **SOLID**. Those principles of OOP consist of:
- **S**: Single Responsibility Principle - a class or method should serve a single purpose.
- **O**: Open/closed Principle - classes or methods should be open for extension, but closed for modification
- **L**: Liskov substitution principle - replacing any instances of a parent class with an instance of one of its children without creating any unexpected or incorrect behaviors.
- **I**: Interface Segregation Principle - any client specific classes are better than one general purpose class. Less relevant in dynamic languages.
- **D**: Dependency Inversion Principle - High-level modules should not depend on low-level modules. Both should depend on abstractions. Abstractions should not depend upon details. Details should depend upon abstractions.

Second one is **LoD**, or **The Law of Demeter**:
- The Law of Demeter, or Principle of Least Knowledge is a well-known software design principle for reducing coupling between collaborating objects.

The code you write should have the following qualities.
- **T**ransparent The consequences of change should be obvious in the code that is changing and in distant code that relies upon it;
- **R**easonable The cost of any change should be proportional to the benefits the change achieves;
- **U**sable Existing code should be usable in new and unexpected contexts;
- **E**xemplary The code itself should encourage those who change it to perpetuate these qualities;

Code that is Transparent, Reasonable, Usable, and Exemplary (**TRUE**) not only meets today’s needs but can also be changed to meet the needs of the future. The first step in creating code that is TRUE is to ensure that each class has a single, well-defined responsibility.

And the most important part is testing:
- **BDD** - Behavior-driven development is a software development practice of working in a short feedback loop, where we consistently apply test-driven development to every new feature we are exploring and working on.
- **TDD** - Test-driven development is a programming technique that requires you to write test.

[dry]: https://en.wikipedia.org/wiki/Don%27t_repeat_yourself
[kiss]: https://en.wikipedia.org/wiki/KISS_principle
[yagni]: https://en.wikipedia.org/wiki/You_aren%27t_gonna_need_it
[eyodf]: https://en.wikipedia.org/wiki/Eating_your_own_dog_food
