import random

import simpy


class StatisticValue:
    def __init__(self, env):
        self.env = env
        self._value = 0
        self._max_value = self._value
        self._history = {}  # [time: value, ...]

    @property
    def value(self):
        return self._value

    @property
    def max_value(self):
        return self._max_value

    @property
    def history(self):
        return sorted(self._history.items(), key=lambda x: x[0])

    def __iadd__(self, other):
        self._value += other
        self._history[self.env.now] = self.value
        self._max_value = max(self.value, self.max_value)

        return self

    def __isub__(self, other):
        self._value -= other
        self._history[self.env.now] = self.value
        return self


class Patient:
    all_created = []

    def __init__(self, index: int, enter: float):
        """
        Пациент.

        Args:
            index: Номер пациента.
            enter: Время входа в поликлинику.
        """
        self.all_created.append(self)
        self.index: int = index
        self.enter: float = enter
        self.exit: float = None

        # Примеры элементов
        # {'type': 'therapist', 'waiting_time': 0, 'service_time': 10.1}
        # {'type': 'doctor', 'waiting_time': 5.1, 'service_time': 20.6}
        self._visits = []

    @property
    def visits(self) -> list:
        return self._visits

    def add_visit(self, type_: str, waiting_time: float, service_time: float):
        if type_ not in ('therapist', 'doctor'):
            raise ValueError(type_)

        waiting_time = 0 if waiting_time < 1 else waiting_time
        service_time = 0 if service_time < 1 else service_time

        self._visits.append({
            'type': type_,
            'waiting_time': waiting_time,
            'service_time': service_time,
        })

    def __str__(self):
        return f'Пациент {self.index}(визитов: {len(self.visits)})'

    def __repr__(self):
        return str(self)


class Polyclinic:
    def __init__(self, registry_time, env=None):
        if env is None:
            self.env = simpy.Environment()
        else:
            self.env = env
        self.r = random.Random()
        self.r.seed(42)

        # Интенсивность входящего потока.
        self.intensity = 65 / 60 / 60  # человек в секунду.

        # Регистратура.
        self.registry_time = registry_time
        self.registry = simpy.Resource(self.env)
        self.probability_visiting_therapist = 0.75

        # Терапевты.
        self.therapists_number = 8
        self.therapists = simpy.Resource(
            self.env,
            capacity=self.therapists_number,
        )

        # Узкопрофильные специалисты.
        self.doctors_number = 10
        self.doctors = [simpy.Resource(self.env)
                        for _ in range(self.doctors_number)]

        self.probability_continue_service = 0.2

        self.queue_at_registry = StatisticValue(self.env)
        self.queue_at_therapist = StatisticValue(self.env)
        self.queue_at_doctors = [StatisticValue(self.env)
                                 for _ in range(self.doctors_number)]

    @property
    def new_patient_timeout(self):
        return 1 / self.intensity

    @property
    def registry_process_time(self):
        return self.registry_time(self.r.random())

    def must_visit_therapist(self):
        return self.r.random() <= self.probability_visiting_therapist

    @property
    def therapist_process_time(self):
        return self.r.randint(5 * 60, 15 * 60)

    @property
    def doctor_process_time(self):
        mu = 15 * 60
        sigma = 2.5 * 60
        return self.r.normalvariate(mu, sigma)

    def must_continue_service(self):
        return self.r.random() <= self.probability_continue_service

    def visit_registry(self):
        """Посещение регистратуры."""
        with self.registry.request() as request:

            if self.registry.count:
                self.queue_at_registry += 1
                yield request
                self.queue_at_registry -= 1

            else:
                yield request

            yield self.env.timeout(self.registry_process_time)

    def visit_therapist(self, patient: Patient):
        """Посещение свободного терапевта."""
        with self.therapists.request() as request:
            if self.therapists.count:
                self.queue_at_therapist += 1
                time = self.env.now

                yield request

                waiting_time = self.env.now - time
                self.queue_at_therapist -= 1

            else:
                yield request
                waiting_time = 0

            time = self.env.now
            yield self.env.timeout(self.therapist_process_time)
            service_time = self.env.now - time

            patient.add_visit(
                type_='therapist',
                waiting_time=waiting_time,
                service_time=service_time,
            )

    def visit_doctor(self, patient: Patient, index=None):
        """Посещение узконаправленного специалиста."""
        if index is None:
            index = self.r.randint(0, self.doctors_number - 1)

        doctor = self.doctors[index]

        with doctor.request() as request:
            if doctor.count:
                self.queue_at_doctors[index] += 1
                time = self.env.now

                yield request

                waiting_time = self.env.now - time
                self.queue_at_doctors[index] -= 1

            else:
                yield request
                waiting_time = 0

            time = self.env.now
            yield self.env.timeout(self.doctor_process_time)
            service_time = self.env.now - time

            patient.add_visit(
                type_='therapist',
                waiting_time=waiting_time,
                service_time=service_time,
            )
